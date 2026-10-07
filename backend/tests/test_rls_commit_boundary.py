"""
RED phase for issue #50, second half: the commit-then-read RLS boundary.

The defect under test
---------------------
``app/api/deps.py:get_db`` binds ``app.current_user_id`` with ``SET LOCAL``
once, at request start (``bind_rls_context``). ``SET LOCAL`` is
transaction-scoped in PostgreSQL -- it is reverted at COMMIT. Handlers that
``await db.commit()`` and then read the SAME RLS-protected table again open
a NEW transaction with the GUC unset, and with ENABLE+FORCE ROW LEVEL
SECURITY that is default-deny:

* owner policy: ``app_current_user_id()`` returns NULL, so
  ``owner_user_id = NULL`` is not true -> 0 rows;
* service policy: ``current_setting('app.current_user_id', true) = '0'`` is
  NULL, not '0' -> 0 rows.

The read therefore misses, and SQLAlchemy's follow-up ``Session.refresh()``
raises ``InvalidRequestError`` ("Could not refresh instance"), which the
endpoint surfaces as HTTP 500 instead of its success status.

What makes these tests able to SEE it
-------------------------------------
Everything runs inside the ``rls_lane`` fixture (tests/conftest_rls.py),
which removes the two masks described there:

* the conftest ``after_begin`` listener that re-binds the service GUC '0'
  on every ORM BEGIN, and
* the SUPERUSER + BYPASSRLS test role the app's engine would otherwise use.

``get_db`` itself is NOT overridden: the handler receives the real session
with the real (once-per-request) GUC binding, so the reproduction is the
production path, not a simulation of it.

EXPECTED RESULT OF THIS FILE, AS WRITTEN: the per-site tests FAIL. The
control tests PASS. That asymmetry is the deliverable -- these tests are
the acceptance criteria for the fix phase. Nothing under ``app/`` is
changed here.
"""
from __future__ import annotations

import ast
import io
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.exc import InvalidRequestError

from app.api.deps import get_runner
from app.core.config import get_settings
from app.core.security import create_access_token
from app.db.models import (
    RecruiterCandidate,
    RecruiterCandidateCV,
    RecruiterConsent,
    Subscription,
    User,
    UserCV,
)
from app.main import app

# ---------------------------------------------------------------------------
# Clients
# ---------------------------------------------------------------------------


@pytest.fixture
async def rls_http():
    """HTTP client that reports the endpoint's REAL status code.

    ``raise_app_exceptions=False`` so an unhandled ``InvalidRequestError``
    becomes the 500 a production server would return, instead of being
    re-raised into the test. That is what lets these tests assert on the
    documented success status (201/200/202) rather than on a traceback.
    """
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def strict_http():
    """HTTP client that re-raises, used only to pin the exception signature."""
    transport = ASGITransport(app=app, raise_app_exceptions=True)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ---------------------------------------------------------------------------
# Auth: a REAL JWT, not a dependency override
# ---------------------------------------------------------------------------
#
# ``app/main.py`` mounts the recruiter routers with a router-level
# ``Depends(verify_api_key)``, and ``verify_api_key`` calls
# ``get_current_user(api_key_header)`` as a PLAIN FUNCTION
# (``app/api/deps.py:295``). A ``dependency_overrides`` entry is therefore
# invisible to those routers -- they answer 401 no matter what the override
# says. A real signed token is both the only thing that works here and the
# more faithful choice: with it, NOTHING is overridden. The session, the
# principal and the single request-scoped GUC binding are 100% production.
# (tests/test_adaptation_endpoints.py uses the override pattern, which is
# fine for routers that only declare ``Depends(get_current_user)`` directly,
# but it silently cannot reach a router-level ``verify_api_key``.)


def _auth_headers(user: User) -> dict[str, str]:
    """A real bearer token for ``user`` (``sub``/``role`` per deps._try_jwt)."""
    token = create_access_token({"sub": str(user.id), "role": user.role})
    return {"Authorization": f"Bearer {token}"}


def _consent_payload(user: User, tos_version: str) -> dict[str, Any]:
    """The body POST /v1/recruiter/consent accepts today (post-#78).

    With ``current_user`` wired through ``Depends(get_current_user)``
    (``recruiter_consent.py:42``) the request shape collapses to ``ConsentRequest``
    fields only -- no ``body`` wrapper, no client-supplied ``current_user``.
    The handler pulls the acting principal from the JWT (header), so this
    payload no longer needs the user's id to make the reproduction honest:
    the JWT IS the identity source now. Sites 5 and 6 below already pass
    a real JWT via ``_auth_headers(user)``; the body here is exactly what a
    real frontend (``apiClient.giveConsent``) sends.
    """
    return {
        "accept_tos": True,
        "good_faith_declaration": True,
        "tos_version": tos_version,
    }


# ---------------------------------------------------------------------------
# Seeding -- the "service / superuser" leg
# ---------------------------------------------------------------------------
#
# Seeding goes through `clean_db.session_factory`, whose engine connects as
# the test SUPERUSER, so it bypasses RLS entirely and can write every row the
# endpoints need to read. That mirrors production's provisioning/MCP path and
# is the correct contrast to the request leg, which runs as a real non-zero
# user id under a genuine owner policy. The request leg never sees these
# connections.


async def _seed_user(
    clean_db, email: str, role: str = "job_seeker"
) -> User:
    async with clean_db.session_factory() as session:
        user = User(
            email=email,
            password_hash="x",
            role=role,
            full_name=email.split("@")[0].title(),
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        session.expunge(user)
        return user


async def _seed_cv(clean_db, owner_user_id: int, *, with_text: bool) -> UserCV:
    async with clean_db.session_factory() as session:
        cv = UserCV(
            owner_user_id=owner_user_id,
            original_filename="cv.pdf",
            detected_locale="es",
            # `raw_text=None` keeps the PATCH path off the embedding provider
            # (`recalc_embedding` returns early on no text). The RLS boundary
            # under test is identical either way.
            raw_text="Jane Doe. Senior Backend Engineer." if with_text else None,
            structured={
                "full_name": "Owner",
                "skills": ["Python"],
                "experience": [],
                "education": [],
            },
            content_version=1,
        )
        session.add(cv)
        await session.commit()
        await session.refresh(cv)
        session.expunge(cv)
        return cv


async def _seed_subscription(
    clean_db, user_id: int, plan: str = "job_seeker_monthly"
) -> Subscription:
    async with clean_db.session_factory() as session:
        sub = Subscription(
            user_id=user_id,
            plan=plan,
            status="active",
            stripe_subscription_id=f"sub_{user_id}",
        )
        session.add(sub)
        await session.commit()
        await session.refresh(sub)
        session.expunge(sub)
        return sub


async def _seed_consent(clean_db, user_id: int) -> RecruiterConsent:
    async with clean_db.session_factory() as session:
        consent = RecruiterConsent(
            user_id=user_id,
            accepted_at=datetime.now(UTC),
            tos_version="v1.2",
        )
        session.add(consent)
        await session.commit()
        await session.refresh(consent)
        session.expunge(consent)
        return consent


async def _seed_candidate(clean_db, recruiter_id: int) -> RecruiterCandidate:
    async with clean_db.session_factory() as session:
        candidate = RecruiterCandidate(
            recruiter_id=recruiter_id,
            full_name="Existing Candidate",
            email="existing@example.com",
        )
        session.add(candidate)
        await session.commit()
        await session.refresh(candidate)
        session.expunge(candidate)
        return candidate


async def _seed_candidate_with_cv(clean_db, recruiter_id: int) -> RecruiterCandidate:
    """A candidate that already owns a parsed CV row.

    ``match_candidate`` reads ``RecruiterCandidateCV`` by ``candidate.cv_id`` and
    422s with ``PDF_NO_TEXT`` when there is none (recruiter_candidates.py:490-501),
    so the CV has to be seeded or the request never reaches the commit under test.
    """
    async with clean_db.session_factory() as session:
        cv = RecruiterCandidateCV(
            original_filename="cv.pdf",
            raw_text=(
                "Jane Doe. Senior Backend Engineer with Python, FastAPI and AWS "
                "experience building data pipelines and REST services."
            ),
        )
        session.add(cv)
        await session.commit()
        await session.refresh(cv)

        candidate = RecruiterCandidate(
            recruiter_id=recruiter_id,
            full_name="Candidate With CV",
            email="withcv@example.com",
            cv_id=cv.id,
        )
        session.add(candidate)
        await session.commit()
        await session.refresh(candidate)
        session.expunge(candidate)
        return candidate


# ---------------------------------------------------------------------------
# PDF / payload helpers
# ---------------------------------------------------------------------------


def _pdf_bytes(
    text: str = (
        "Jane Doe is a Senior Backend Engineer with Python, FastAPI and AWS "
        "experience building data pipelines and REST services."
    ),
) -> bytes:
    """A minimal single-page PDF with extractable text.

    Built inline (no shared fixture exists outside tests/test_audit.py) so
    this file stays self-contained: a private copy of a test helper must not
    become a cross-module import contract. The text clears the 50-character
    floor ``pdf_parser.parse_pdf`` enforces before it will accept a PDF.
    """
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(f"{i} 0 obj\n".encode() + body + b"\nendobj\n")
    xref_pos = out.tell()
    out.write(b"xref\n0 %d\n" % (len(objects) + 1))
    out.write(b"0000000000 65535 f \n")
    for off in offsets:
        out.write(b"%010d 00000 n \n" % off)
    out.write(
        b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n"
        % (len(objects) + 1, xref_pos)
    )
    return out.getvalue()


_STRUCTURED = {
    "full_name": "Jane Doe",
    "email": "jane@example.com",
    "skills": ["Python", "FastAPI"],
    "experience": [
        {
            "title": "Senior Backend Engineer",
            "company": "Acme",
            "dates": "2020-2024",
            "description": "Built Python services.",
        }
    ],
    "education": [],
    "languages": [],
}

# Pastes that clear the length floors the two sites below enforce: the match
# handler rejects jd_text shorter than 50 chars (recruiter_candidates.py:455)
# and the audit handler rejects cv_text shorter than 50 chars (audit.py:MIN_CV_TEXT_LENGTH).
_JD = (
    "Senior Backend Engineer. You will build and maintain Python services with "
    "FastAPI, own PostgreSQL schemas, and ship to production with CI."
)
_CV_TEXT = (
    "Jane Doe. Senior Backend Engineer with Python, FastAPI and AWS experience "
    "building data pipelines and REST services."
)


class _FakeRunner:
    """Records spawned jobs without touching the DB.

    Reaches the DB only AFTER the endpoint commits, so it is not the thing
    under test here -- it just keeps the LLM out of the picture.
    """

    def __init__(self) -> None:
        self.calls: list[int] = []

    async def run(self, adaptation_id: int) -> None:
        self.calls.append(adaptation_id)


@asynccontextmanager
async def _adaptation_enabled() -> AsyncIterator[None]:
    settings = get_settings()
    original = settings.adaptation_enabled
    settings.adaptation_enabled = True
    try:
        yield
    finally:
        settings.adaptation_enabled = original


@asynccontextmanager
async def _fake_runner() -> AsyncIterator[_FakeRunner]:
    runner = _FakeRunner()
    app.dependency_overrides[get_runner] = lambda: runner
    try:
        yield runner
    finally:
        app.dependency_overrides.pop(get_runner, None)


def _why(response: Any) -> str:
    return f"{response.status_code} {response.text[:300]}"


# ===========================================================================
# CONTROLS -- these must PASS. Without them the failures below are noise.
# ===========================================================================


class TestLaneIsFaithful:
    """The lane reproduces production RLS. Nothing else here is about #50.

    If any of these fail, the endpoint tests are meaningless: they would be
    running under a superuser or under the service bypass and would pass for
    the wrong reason (or, worse, fail for an unrelated reason).
    """

    async def test_app_connection_runs_as_the_non_superuser_rls_role(
        self, rls_lane, clean_db
    ) -> None:
        """Mask 2 is gone: the app's engine no longer runs as SUPERUSER."""
        async with rls_lane.engine.connect() as conn:
            who = (await conn.execute(text("SELECT current_user"))).scalar_one()
            superuser, bypassrls = (
                await conn.execute(
                    text(
                        "SELECT rolsuper, rolbypassrls FROM pg_roles "
                        "WHERE rolname = current_user"
                    )
                )
            ).one()

        assert who == rls_lane.role
        assert superuser is False
        assert bypassrls is False

    async def test_no_service_guc_is_rebound_on_a_fresh_transaction(
        self, rls_lane, clean_db
    ) -> None:
        """Mask 1 is gone: the conftest after_begin re-bind no longer fires.

        This is the single most important control. A session opened here and
        never touched binds nothing, so any endpoint that relied on the
        listener to survive a COMMIT is now visible.
        """
        async with rls_lane.session() as session:
            guc = (
                await session.execute(
                    text("SELECT current_setting('app.current_user_id', true)")
                )
            ).scalar_one()

        assert guc is None, (
            f"expected no RLS GUC on a fresh ORM transaction, got {guc!r}; the "
            "conftest service listener is still rebinding it"
        )

    async def test_owner_policy_denies_a_cross_user_read(
        self, rls_lane, clean_db
    ) -> None:
        """With the real GUC bound, user A cannot see user B's CV."""
        a = await _seed_user(clean_db, "ctl-a@test.com")
        b = await _seed_user(clean_db, "ctl-b@test.com")
        cv_a = await _seed_cv(clean_db, a.id, with_text=False)
        cv_b = await _seed_cv(clean_db, b.id, with_text=False)

        async with rls_lane.as_user(a.id, "job_seeker") as session:
            visible = (
                (
                    await session.execute(
                        select(UserCV.id).where(
                            UserCV.id.in_([cv_a.id, cv_b.id])
                        )
                    )
                )
                .scalars()
                .all()
            )

        assert visible == [cv_a.id], (
            "RLS did not deny the cross-user read; the lane is not faithful"
        )

    async def test_unbound_guc_denies_even_the_owners_own_row(
        self, rls_lane, clean_db
    ) -> None:
        """The exact post-COMMIT state: no GUC, so even own rows vanish.

        This is what ``Session.refresh()`` runs into after the handler's
        ``commit()`` reverts the request-scoped ``SET LOCAL``.
        """
        a = await _seed_user(clean_db, "ctl-self@test.com")
        cv_a = await _seed_cv(clean_db, a.id, with_text=False)

        async with rls_lane.session() as session:
            rows = (
                (await session.execute(select(UserCV.id).where(UserCV.id == cv_a.id)))
                .scalars()
                .all()
            )

        assert rows == [], (
            "an unbound GUC still saw the owner's own row; the lane is not "
            "faithful (superuser or service listener leaked back in?)"
        )


# ===========================================================================
# THE DEFECT -- one test per commit-then-read boundary. All of these FAIL.
# ===========================================================================


class TestCommitThenReadBoundaries:
    """Each handler: INSERT/UPDATE -> ``commit()`` -> read the SAME table.

    The documented success status is asserted. Today the read happens in an
    unbound transaction, sees no row, and the endpoint returns 500.
    """

    # -- site 1 ------------------------------------------------------------

    async def test_site1_post_cvs_pdf_upload_returns_201(
        self, rls_lane, rls_http, clean_db
    ) -> None:
        """POST /v1/cvs (PDF) -- app/api/v1/cvs.py:105-107, table users_cvs."""
        user = await _seed_user(clean_db, "site1@test.com")

        response = await rls_http.post(
            "/v1/cvs",
            files={"file": ("cv.pdf", _pdf_bytes(), "application/pdf")},
            headers=_auth_headers(user),
        )

        assert response.status_code == 201, (
            f"POST /v1/cvs should return 201; got {_why(response)}. The commit "
            "at cvs.py:106 reverts the request-scoped SET LOCAL, so the "
            "refresh() at cvs.py:107 reads users_cvs with no GUC and 0 rows."
        )

    # -- site 2 ------------------------------------------------------------

    async def test_site2_post_cvs_structured_returns_201(
        self, rls_lane, rls_http, clean_db
    ) -> None:
        """POST /v1/cvs/structured -- cvs.py:137-139, table users_cvs."""
        user = await _seed_user(clean_db, "site2@test.com")

        response = await rls_http.post(
            "/v1/cvs/structured",
            json={"structured": _STRUCTURED, "original_filename": "cv.json"},
            headers=_auth_headers(user),
        )

        assert response.status_code == 201, (
            f"POST /v1/cvs/structured should return 201; got {_why(response)}. "
            "Commit at cvs.py:138 reverts SET LOCAL; refresh() at cvs.py:139 "
            "reads users_cvs with no GUC."
        )

    # -- site 3 ------------------------------------------------------------

    async def test_site3_patch_cv_returns_200(
        self, rls_lane, rls_http, clean_db
    ) -> None:
        """PATCH /v1/cvs/{cv_id} -- cvs.py:266-267, table users_cvs."""
        user = await _seed_user(clean_db, "site3@test.com")
        cv = await _seed_cv(clean_db, user.id, with_text=False)

        response = await rls_http.patch(
            f"/v1/cvs/{cv.id}",
            json={"structured": {**_STRUCTURED, "skills": ["Rust"]}},
            headers=_auth_headers(user),
        )

        assert response.status_code == 200, (
            f"PATCH /v1/cvs/{{id}} should return 200; got {_why(response)}. "
            "Commit at cvs.py:266 reverts SET LOCAL; refresh() at cvs.py:267 "
            "reads users_cvs with no GUC."
        )

    # -- site 4 ------------------------------------------------------------

    async def test_site4_post_adaptations_returns_202(
        self, rls_lane, rls_http, clean_db
    ) -> None:
        """POST /v1/adaptations -- adaptations.py:330 + 367, cv_adaptations."""
        user = await _seed_user(clean_db, "site4@test.com")
        await _seed_subscription(clean_db, user.id)
        cv = await _seed_cv(clean_db, user.id, with_text=True)

        async with _adaptation_enabled(), _fake_runner():
            response = await rls_http.post(
                "/v1/adaptations",
                json={
                    "cv_id": cv.id,
                    "jd_text": "Looking for a Senior Backend Engineer with Python.",
                },
                headers=_auth_headers(user),
            )

        assert response.status_code == 202, (
            f"POST /v1/adaptations should return 202; got {_why(response)}. "
            "Commit at adaptations.py:330 reverts SET LOCAL; refresh() at "
            "adaptations.py:367 reads cv_adaptations with no GUC."
        )

    # -- site 5 / 6 --------------------------------------------------------
    #
    # These two sites previously sat behind a SECOND, independent defect:
    # `recruiter_consent.py:42` declared `current_user: CurrentUser` with no
    # `Depends(...)`, so FastAPI treated it as a REQUIRED BODY FIELD. The
    # endpoint's own OpenAPI contract was
    # `{"body": {...ConsentRequest}, "current_user": {...CurrentUser}}` and
    # a real client sending a flat ConsentRequest got 422 -- masking the
    # second issue (#78), that the handler took the acting principal from
    # a CLIENT-CONTROLLED body field rather than the JWT.
    #
    # Both defects are now fixed: ``current_user: CurrentUser = Depends(...)``
    # pulls from the JWT, and the body is just ``ConsentRequest`` fields. The
    # payload helper ``_consent_payload`` above returns that shape. Sites 5
    # and 6 below are now RLS-boundary tests, full stop.

    async def test_site5_post_recruiter_consent_update_returns_201(
        self, rls_lane, rls_http, clean_db
    ) -> None:
        """POST /v1/recruiter/consent, re-consent path -- recruiter_consent.py:95-96.

        Seeded with an existing consent row so the handler takes the
        UPDATE branch (flush -> commit at :95 -> refresh at :96).
        """
        user = await _seed_user(clean_db, "site5@test.com", role="recruiter")
        await _seed_consent(clean_db, user.id)

        response = await rls_http.post(
            "/v1/recruiter/consent",
            json=_consent_payload(user, "v1.3"),
            headers=_auth_headers(user),
        )

        assert response.status_code == 201, (
            f"POST /v1/recruiter/consent (re-consent) should return 201; got "
            f"{_why(response)}. Commit at recruiter_consent.py:95 reverts SET "
            "LOCAL; refresh() at :96 reads recruiter_consents with no GUC."
        )

    async def test_site6_post_recruiter_consent_create_returns_201(
        self, rls_lane, rls_http, clean_db
    ) -> None:
        """POST /v1/recruiter/consent, new-consent path -- recruiter_consent.py:121-122.

        No consent row seeded, so the handler takes the INSERT branch
        (flush -> commit at :121 -> refresh at :122).
        """
        user = await _seed_user(clean_db, "site6@test.com", role="recruiter")

        response = await rls_http.post(
            "/v1/recruiter/consent",
            json=_consent_payload(user, "v1.2"),
            headers=_auth_headers(user),
        )

        assert response.status_code == 201, (
            f"POST /v1/recruiter/consent (new consent) should return 201; got "
            f"{_why(response)}. Commit at recruiter_consent.py:121 reverts SET "
            "LOCAL; refresh() at :122 reads recruiter_consents with no GUC."
        )

    # -- site 7 ------------------------------------------------------------

    async def test_site7_post_recruiter_candidate_returns_201(
        self, rls_lane, rls_http, clean_db
    ) -> None:
        """POST /v1/recruiter/candidates -- recruiter_candidates.py:184-186.

        Success status is 201 (the decorator at ``recruiter_candidates.py:102``
        declares ``status_code=201``). The handler uses no ``refresh()`` after
        commit -- it relies on ``expire_on_commit=False`` to keep the inserted
        instance current, the same fix that closed #50 on the other endpoints.

        Previously ``XFAIL`` for issue #77: ``body: CandidateCreate`` next to
        ``file: UploadFile = File(None)`` produced a multipart contract with a
        required field literally named ``body`` on FastAPI 0.141.1. The
        handler is reachable now -- the four flat candidate fields are read
        individually with ``Form(...)`` (``recruiter_candidates.py:105-108``)
        and the file with ``File(None)``. The marker was removed when #77
        landed; if this test fails it must fail loudly, so the strict=False
        xfail is gone and this test is plain ``async def``.
        """
        recruiter = await _seed_user(clean_db, "site7@test.com", role="recruiter")
        await _seed_consent(clean_db, recruiter.id)

        response = await rls_http.post(
            "/v1/recruiter/candidates",
            data={"full_name": "Ada Lovelace", "email": "ada@example.com"},
            files={
                "_": (None, ""),  # only to force multipart; FastAPI ignores it
                "file": ("cv.pdf", _pdf_bytes(), "application/pdf"),
            },
            headers=_auth_headers(recruiter),
        )

        assert response.status_code == 201, (
            f"POST /v1/recruiter/candidates should return 201; got "
            f"{_why(response)}. Commit at recruiter_candidates.py:176 reverts "
            "SET LOCAL; refresh() at :177 reads recruiter_candidates with no "
            "GUC -- but see the docstring: today this 422s before the handler "
            "runs."
        )

    # -- site 8 ------------------------------------------------------------

    async def test_site8_patch_recruiter_candidate_returns_200(
        self, rls_lane, rls_http, clean_db
    ) -> None:
        """PATCH /v1/recruiter/candidates/{id} -- recruiter_candidates.py:392-393."""
        recruiter = await _seed_user(clean_db, "site8@test.com", role="recruiter")
        await _seed_consent(clean_db, recruiter.id)
        candidate = await _seed_candidate(clean_db, recruiter.id)

        response = await rls_http.patch(
            f"/v1/recruiter/candidates/{candidate.id}",
            json={"notes": "Called on Monday"},
            headers=_auth_headers(recruiter),
        )

        assert response.status_code == 200, (
            f"PATCH /v1/recruiter/candidates/{{id}} should return 200; got "
            f"{_why(response)}. Commit at recruiter_candidates.py:392 reverts "
            "SET LOCAL; refresh() at recruiter_candidates.py:393 reads "
            "recruiter_candidates with no GUC."
        )

    # -- site 9 ------------------------------------------------------------

    async def test_site9_post_recruiter_match_returns_200(
        self, rls_lane, rls_http, clean_db
    ) -> None:
        """POST /v1/recruiter/candidates/{id}/match -- recruiter_candidates.py:547-548.

        Success status is 200: the decorator declares no ``status_code``, so
        FastAPI's POST default applies (``recruiter_candidates.py:441``).

        A paid subscription is required because ``get_plan_limits`` returns
        ``matches_per_month=0`` for a recruiter on the free plan
        (``tier_limits.get_plan_limits``), which the handler turns into a 402
        before the match ever runs.

        This site carried TWO independent defects, both of which made it
        return 500, so the status code alone could not tell them apart.

        1. The #50 boundary: ``db.refresh(analysis)`` on ``recruiter_analyses``
           after COMMIT. Fixed by removing the redundant refresh.
        2. A response-schema defect: ``MatchAnalysis`` yields
           ``strengths``/``gaps`` as ``list[str]``
           (``app/llm/schemas.py``), they are stored verbatim in the JSON
           column, but ``CandidateMatchResponse`` declared both as
           ``dict | None`` (``app/schemas/recruiter.py``), so serialization
           raised ``pydantic.ValidationError``. Only the 404 path was covered
           anywhere in the suite (``test_recruiter.py:322``), which is why
           neither defect was noticed. Fixed by correcting the annotations to
           ``list[str] | None``.

        The assertion below proves neither defect 500s again. It does NOT pin
        the shape of the payload -- for that see
        ``test_site9_response_returns_strengths_and_gaps_as_lists``.
        """
        recruiter = await _seed_user(clean_db, "site9@test.com", role="recruiter")
        await _seed_consent(clean_db, recruiter.id)
        await _seed_subscription(clean_db, recruiter.id, plan="recruiter_starter")
        candidate = await _seed_candidate_with_cv(clean_db, recruiter.id)

        response = await rls_http.post(
            f"/v1/recruiter/candidates/{candidate.id}/match",
            json={"jd_text": _JD},
            headers=_auth_headers(recruiter),
        )

        assert response.status_code == 200, (
            f"POST /v1/recruiter/candidates/{{id}}/match should return 200; got "
            f"{_why(response)}. See the docstring: this site carried both the "
            "#50 refresh boundary and a response-schema defect."
        )

    async def test_site9_response_returns_strengths_and_gaps_as_lists(
        self, rls_lane, rls_http, clean_db
    ) -> None:
        """Pin the SHAPE of the match payload, which the 200 assertion cannot.

        ``CandidateMatchResponse.strengths``/``.gaps`` were declared
        ``dict | None`` while the producer (``app.llm.schemas.MatchAnalysis``)
        emits ``list[str]``. That mismatch was a live 500. Correcting the
        annotations fixed it -- but a status-code-only test would stay green if
        the shape regressed to something Pydantic coerces silently.

        This asserts the wire format is an array of strings, which is what the
        LLM adapter produces and what the JSON column stores.
        """
        recruiter = await _seed_user(clean_db, "site9shape@test.com", role="recruiter")
        await _seed_consent(clean_db, recruiter.id)
        await _seed_subscription(clean_db, recruiter.id, plan="recruiter_starter")
        candidate = await _seed_candidate_with_cv(clean_db, recruiter.id)

        response = await rls_http.post(
            f"/v1/recruiter/candidates/{candidate.id}/match",
            json={"jd_text": _JD},
            headers=_auth_headers(recruiter),
        )

        assert response.status_code == 200, f"got {_why(response)}"
        body = response.json()

        for field in ("strengths", "gaps"):
            value = body[field]
            assert isinstance(value, list), (
                f"{field} must be a JSON array, got {type(value).__name__}. "
                "The producer is MatchAnalysis (list[str]); if this regressed "
                "to a mapping, CandidateMatchResponse's annotation is lying "
                "again and the next mismatch will be a 500 again."
            )
            assert all(isinstance(item, str) for item in value), (
                f"{field} must contain only strings, got {value!r}"
            )

    async def test_site9_no_longer_refreshes_recruiter_analyses_after_commit(
        self, rls_lane, strict_http, clean_db
    ) -> None:
        """The #50 signal for site 9, which the status code cannot express.

        Before the fix this raised
        ``InvalidRequestError: Could not refresh instance '<RecruiterAnalysis ...>'``
        from ``recruiter_candidates.py:548``. ``strict_http`` re-raises
        instead of swallowing it into a 500, so the exception identity is
        observable -- which matters because this endpoint 500s on both sides of
        the fix (see the sibling test's docstring).

        What is asserted is the ABSENCE of the defect's own exception. The
        request now succeeds with a 200 (the response-schema defect is fixed
        too), but this test stays the precise #50 signal: it distinguishes
        "RLS denied the post-commit read" from any other 500, which the status
        assertion alone cannot do.

        Note what is deliberately NOT asserted here: that the analysis row
        reached the database. ``db.commit()`` flushes and commits the INSERT
        before ``refresh()`` ever runs, so the row is present both before and
        after the fix -- counting it proves nothing about #50.
        """
        recruiter = await _seed_user(clean_db, "site9b@test.com", role="recruiter")
        await _seed_consent(clean_db, recruiter.id)
        await _seed_subscription(clean_db, recruiter.id, plan="recruiter_starter")
        candidate = await _seed_candidate_with_cv(clean_db, recruiter.id)

        try:
            response = await strict_http.post(
                f"/v1/recruiter/candidates/{candidate.id}/match",
                json={"jd_text": _JD},
                headers=_auth_headers(recruiter),
            )
        except InvalidRequestError as exc:  # pragma: no cover - the defect
            pytest.fail(
                f"issue #50: the handler still reads recruiter_analyses after "
                f"COMMIT and RLS denies it -- {exc}"
            )
        except Exception as exc:  # noqa: BLE001 - any other failure is progress
            # Reaching here means the RLS boundary is no longer the blocker.
            # The string check also catches the defect when it arrives wrapped
            # (Starlette's ExceptionGroup re-raises it as a group).
            assert "Could not refresh" not in str(exc), (
                f"issue #50 surfaced in a wrapped form: {exc}"
            )
        else:
            assert response.status_code == 200, (
                f"expected 200 once both defects are fixed; got {_why(response)}"
            )

    # -- site 10 -----------------------------------------------------------

    async def test_site10_post_anonymous_audit_returns_200(
        self, rls_lane, rls_http, clean_db
    ) -> None:
        """POST /v1/audit/anonymous -- audit.py:242-243, table audit_uploads.

        Success status is 200, declared explicitly on the decorator
        (``audit.py:122``).

        This is the one site in the file with NO JWT and no seeded rows, and
        that is the real shape of the endpoint, not a shortcut: it is the
        public funnel, it declares no auth dependency at all, and it opens its
        OWN session via ``get_session_context()`` which it re-binds with
        ``set_rls_anonymous(session)`` (audit.py:154-156) rather than inheriting
        a request-scoped binding. Forcing a token through it would prove
        nothing, and neither would seeding a user: nothing here is owner-scoped.

        The cv-only mode is used (``cv_text``, no ``jd_text``) because it
        exercises the identical persistence tail with one less moving part.
        ``run_audit``'s ``session`` argument is documented as unused
        (``audit_runner.py:72``), so the LLM leg touches no RLS table.
        """
        response = await rls_http.post(
            "/v1/audit/anonymous",
            data={"cv_text": _CV_TEXT},
        )

        assert response.status_code == 200, (
            f"POST /v1/audit/anonymous should return 200; got {_why(response)}. "
            "Commit at audit.py:242 reverts the SET LOCAL issued by "
            "set_rls_anonymous at audit.py:156; refresh() at audit.py:243 "
            "reads audit_uploads with no GUC."
        )


# ===========================================================================
# REGRESSION GUARD -- the structural fix is deferred, so the CLASS can grow back
# ===========================================================================


# Tables under ENABLE + FORCE ROW LEVEL SECURITY, i.e. the ones where a
# post-commit read is denied. Mirrors migration 011 ``_OWNER_TABLES`` plus
# ``recruiter_candidates_cvs`` and ``audit_uploads``; keep in step with it.
_RLS_PROTECTED_TABLES = frozenset(
    {
        "users_cvs",
        "analyses",
        "recruiter_candidates",
        "recruiter_analyses",
        "recruiter_consents",
        "recruiter_candidates_cvs",
        "audit_uploads",
        "subscriptions",
        "payments",
        "usage_counters",
    }
)

# Known-broken sites that predate this guard: a LIVE 500 in the faithful RLS
# lane, each confirmed by raising the handler's own exception --
#   InvalidRequestError: Could not refresh instance '<RecruiterAnalysis ...>'
#   InvalidRequestError: Could not refresh instance '<AuditUpload ...>'
# Both are now FIXED (sites 9 and 10), so this set is empty on purpose: there
# is no remaining post-commit refresh() on an RLS-protected table anywhere in
# app/api/v1. Keep it that way -- add an entry only together with the site
# number that owns it, and delete the entry in the same change that fixes it.
# The assertion below is EQUALITY, not containment, so a stale entry fails
# rather than rotting into a permanent excuse.
_KNOWN_POST_COMMIT_REFRESHES: set[tuple[str, int]] = set()


def _model_to_table() -> dict[str, str]:
    """Map every mapped class in ``app/db/models.py`` to its table name."""
    source = (Path(__file__).parent.parent / "app" / "db" / "models.py").read_text(
        encoding="utf-8"
    )
    mapping: dict[str, str] = {}
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.ClassDef):
            continue
        for stmt in node.body:
            # __tablename__: str = "x"  ->  value is a plain string literal
            if (
                isinstance(stmt, ast.Assign)
                and any(
                    isinstance(t, ast.Name) and t.id == "__tablename__"
                    for t in stmt.targets
                )
                and isinstance(stmt.value, ast.Constant)
                and isinstance(stmt.value.value, str)
            ):
                mapping[node.name] = stmt.value.value
    return mapping


def _refreshed_model(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> str | None:
    """Best-effort: which model class is bound to a refreshed variable.

    Two shapes cover every handler in ``app/api/v1``: a constructor
    assignment (``row = CVAdaptation(...)``) and a lookup
    (``cv = result.scalar_one_or_none()`` off a single ``select(Model)``).
    A miss returns ``None``, which the caller treats as "not provably
    protected" -- a false negative, which is the safe direction here.
    """
    constructors: dict[str, str] = {}
    selected: set[str] = set()
    for node in ast.walk(fn):
        # <var> = <Model>(...)
        if (
            isinstance(node, ast.Assign)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Name)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
        ):
            constructors[node.targets[0].id] = node.value.func.id
        # select(<Model>)
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "select"
            and node.args
            and isinstance(node.args[0], ast.Name)
        ):
            selected.add(node.args[0].id)

    for stmt in ast.walk(fn):
        # await <session>.refresh(<var>)
        if not (
            isinstance(stmt, ast.Expr)
            and isinstance(stmt.value, ast.Await)
            and isinstance(stmt.value.value, ast.Call)
            and isinstance(stmt.value.value.func, ast.Attribute)
            and stmt.value.value.func.attr == "refresh"
        ):
            continue
        args = stmt.value.value.args
        if not args or not isinstance(args[0], ast.Name):
            continue
        var = args[0].id
        if var in constructors:
            return constructors[var]
        if len(selected) == 1:
            return next(iter(selected))
    return None


def _find_post_commit_refreshes() -> list[tuple[str, int, str]]:
    """Every post-commit ``refresh()`` on an RLS-protected table.

    Returns ``(relative_path, line_number, model_class)`` triples.
    """
    tables = _model_to_table()
    api_dir = Path(__file__).parent.parent / "app" / "api" / "v1"
    found: list[tuple[str, int, str]] = []
    for path in sorted(api_dir.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            committed = False
            for stmt in ast.walk(fn):
                if not isinstance(stmt, ast.Expr) or not isinstance(
                    stmt.value, ast.Await
                ):
                    continue
                call = stmt.value.value
                if not isinstance(call, ast.Call) or not isinstance(
                    call.func, ast.Attribute
                ):
                    continue
                if call.func.attr == "commit":
                    committed = True
                elif call.func.attr == "refresh" and committed:
                    model = _refreshed_model(fn)
                    if model and tables.get(model) in _RLS_PROTECTED_TABLES:
                        found.append(
                            (
                                path.relative_to(
                                    Path(__file__).parent.parent
                                ).as_posix(),
                                stmt.lineno,
                                model,
                            )
                        )
                        committed = False
    return found


class TestNoPostCommitRefreshOnRlsTables:
    """No handler may ``refresh()`` an RLS-protected table after ``commit()``.

    The structural fix -- re-binding the GUC after every COMMIT, or moving
    the write to the end of the request -- is deferred. Until then this is
    the only thing stopping the pattern from coming back.
    """

    def test_no_handler_refreshes_an_rls_table_after_commit(self) -> None:
        found = _find_post_commit_refreshes()

        new_ones = [
            entry for entry in found if (entry[0], entry[1]) not in _KNOWN_POST_COMMIT_REFRESHES
        ]
        assert not new_ones, (
            "post-commit refresh() on an RLS-protected table found (issue #50). "
            "After await db.commit() the request-scoped SET LOCAL is gone, so "
            "the refresh opens a new transaction with no GUC, the FORCE RLS "
            "policies deny, and the endpoint 500s. Drop the refresh -- "
            "expire_on_commit=False already keeps the instance current. "
            "Offending sites:\n"
            + "\n".join(f"  {p}:{n}  ({m})" for p, n, m in new_ones)
        )

    def test_known_offenders_list_is_still_accurate(self) -> None:
        """Shrink ``_KNOWN_POST_COMMIT_REFRESHES`` when a site is fixed."""
        found = {(p, n) for p, n, _ in _find_post_commit_refreshes()}

        assert found == _KNOWN_POST_COMMIT_REFRESHES, (
            "the set of known post-commit refreshes changed. New sites: "
            f"{sorted(found - _KNOWN_POST_COMMIT_REFRESHES)}; fixed sites no "
            f"longer present: {sorted(_KNOWN_POST_COMMIT_REFRESHES - found)}. "
            "Add the new ones above, or delete the fixed ones from "
            "_KNOWN_POST_COMMIT_REFRESHES so this file keeps describing reality."
        )

