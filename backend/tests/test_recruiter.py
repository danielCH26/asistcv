"""
Tests for recruiter roster functionality.

These tests cover:
- Consent gate (403 for recruiters without consent)
- Re-consent endpoint
- Candidate CRUD operations
- Candidate ranking
- Issue #78 regression: ``give_consent`` / ``get_consent`` resolve the acting
  user from the JWT, never from a body field.
- Issue #77 regression: ``POST /v1/recruiter/candidates`` accepts the flat
  multipart shape the frontend sends (``client.ts:302-310``), with or
  without a ``file`` field.
"""
import io
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

import app.api.v1.recruiter_candidates as recruiter_candidates_module
from app.core.security import create_access_token
from app.db.models import (
    RecruiterAuditLog,
    RecruiterCandidate,
    RecruiterConsent,
    Subscription,
    User,
)
from app.services.candidate_ranking import (
    calculate_effective_score,
    calculate_recency_decay,
)
from app.services.consent_gate import check_recruiter_consent


class TestConsentGate:
    """Tests for the consent gate dependency."""

    @pytest.mark.asyncio
    async def test_recruiter_without_consent_returns_403(self, test_db):
        """Recruiters without consent should get 403 CONSENT_REQUIRED."""
        from fastapi import HTTPException

        async with test_db.session_factory() as session:
            # Create a recruiter without consent
            user = User(
                email="recruiter@test.com",
                password_hash="hashed",
                role="recruiter",
                full_name="Test Recruiter",
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)

            # Create CurrentUser for recruiter
            from app.api.deps import CurrentUser
            current_user = CurrentUser(id=user.id, name=user.full_name, role="recruiter", auth_method="jwt")

            # Mock session.execute to return no consent
            with patch.object(session, "execute", new_callable=AsyncMock) as mock_execute:
                mock_result = MagicMock()
                mock_result.scalar_one_or_none.return_value = None
                mock_execute.return_value = mock_result

                with pytest.raises(HTTPException) as exc_info:
                    await check_recruiter_consent(current_user, session)

                assert exc_info.value.status_code == 403
                assert exc_info.value.detail == "CONSENT_REQUIRED"

    @pytest.mark.asyncio
    async def test_recruiter_with_consent_passes(self, test_db):
        """Recruiters with consent should pass."""
        from app.api.deps import CurrentUser

        async with test_db.session_factory() as session:
            # Create a recruiter with consent
            user = User(
                email="recruiter_with_consent@test.com",
                password_hash="hashed",
                role="recruiter",
                full_name="Test Recruiter",
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)

            # Use timezone-aware datetime
            consent = RecruiterConsent(
                user_id=user.id,
                accepted_at=datetime.now(UTC).replace(tzinfo=None),  # Make naive for DB
                tos_version="v1.2",
            )
            session.add(consent)
            await session.commit()

            current_user = CurrentUser(id=user.id, name=user.full_name, role="recruiter", auth_method="jwt")

            # Mock session.execute to return consent
            with patch.object(session, "execute", new_callable=AsyncMock) as mock_execute:
                mock_result = MagicMock()
                mock_result.scalar_one_or_none.return_value = consent
                mock_execute.return_value = mock_result

                result = await check_recruiter_consent(current_user, session)
                assert result.id == user.id
                assert result.role == "recruiter"

    @pytest.mark.asyncio
    async def test_non_recruiter_passes_always(self, test_db):
        """Non-recruiters should always pass (no consent check)."""
        from app.api.deps import CurrentUser

        async with test_db.session_factory() as session:
            current_user = CurrentUser(id=1, name="Test User", role="job_seeker", auth_method="jwt")

            # Should pass without checking consent
            result = await check_recruiter_consent(current_user, session)
            assert result.role == "job_seeker"


class TestCandidateRanking:
    """Tests for the candidate ranking algorithm."""

    def test_calculate_recency_decay_never_analysed(self):
        """Candidates never analysed have no decay (1.0)."""
        decay = calculate_recency_decay(None)
        assert decay == 1.0

    def test_calculate_recency_decay_recent_analysis(self):
        """Recently analysed candidates have high decay (close to 1.0)."""
        recent = datetime.now(UTC) - timedelta(days=1)
        decay = calculate_recency_decay(recent)
        assert 0.9 < decay <= 1.0

    def test_calculate_recency_decay_old_analysis(self):
        """Old analyses have significant decay."""
        old = datetime.now(UTC) - timedelta(days=30)
        decay = calculate_recency_decay(old)
        assert 0.3 < decay < 0.4

    def test_calculate_effective_score_basic(self):
        """Basic effective score calculation."""
        score = calculate_effective_score(0.8, datetime.now(UTC) - timedelta(days=1))
        assert 0.7 < score < 0.8

    def test_calculate_effective_score_floor_rule_applied(self):
        """Floor rule should apply when match_score >= 0.7."""
        # Old analysis that would normally decay below floor
        old = datetime.now(UTC) - timedelta(days=60)
        score = calculate_effective_score(0.9, old, apply_floor=True)

        # With floor: floor = 0.5 * 0.9 = 0.45
        # Without floor: 0.9 * exp(-60/30) = 0.9 * 0.135 = 0.1215
        # Should be capped at floor: >= 0.45
        assert score >= 0.45

    def test_calculate_effective_score_floor_not_applied_for_low_scores(self):
        """Floor rule should NOT apply when match_score < 0.7."""
        old = datetime.now(UTC) - timedelta(days=60)
        score = calculate_effective_score(0.5, old, apply_floor=True)

        # Without floor: 0.5 * exp(-60/30) = 0.5 * 0.135 = 0.0675
        # Floor would be 0.5 * 0.5 = 0.25 but shouldn't apply
        assert score < 0.15


class TestRecruiterConsentModel:
    """Tests for RecruiterConsent model."""

    @pytest.mark.asyncio
    async def test_create_consent(self, test_db):
        """Creating a consent record should work."""
        async with test_db.session_factory() as session:
            user = User(
                email="consent_test@test.com",
                password_hash="hashed",
                role="recruiter",
                full_name="Consent Test",
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)

            # Use timezone-naive datetime for DB
            consent = RecruiterConsent(
                user_id=user.id,
                accepted_at=datetime.now(UTC).replace(tzinfo=None),
                tos_version="v1.2",
                ip="127.0.0.1",
                user_agent="Test/1.0",
            )
            session.add(consent)
            await session.commit()

            assert consent.id is not None
            assert consent.user_id == user.id
            assert consent.tos_version == "v1.2"


class TestCandidateModel:
    """Tests for RecruiterCandidate model."""

    @pytest.mark.asyncio
    async def test_create_candidate(self, test_db):
        """Creating a candidate should work."""
        async with test_db.session_factory() as session:
            user = User(
                email="recruiter_candidate@test.com",
                password_hash="hashed",
                role="recruiter",
                full_name="Recruiter Test",
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)

            candidate = RecruiterCandidate(
                recruiter_id=user.id,
                full_name="John Doe",
                email="john@example.com",
                phone="+1234567890",
                notes="Good candidate",
            )
            session.add(candidate)
            await session.commit()

            assert candidate.id is not None
            assert candidate.full_name == "John Doe"
            assert candidate.email == "john@example.com"
            assert candidate.recruiter_id == user.id


class TestCandidateIsolation:
    """Security regression: cross-recruiter candidate isolation.

    Existence-leak rule: a foreign candidate id must be indistinguishable
    from a nonexistent one (404 CANDIDATE_NOT_FOUND), never a 403 that
    would confirm the candidate exists.
    """

    @pytest.mark.asyncio
    async def test_match_other_recruiters_candidate_404(
        self, async_client, clean_db, override_get_session, monkeypatch
    ):
        """recruiter_2 POSTs a match on recruiter_1's candidate -> 404, not 403.

        The endpoint filters by ``recruiter_id == current_user.id`` and raises
        404 when no row matches; this test pins that contract so a refactor
        cannot regress it into a 403 (existence leak) or a 200 (data leak).

        recruiter_2 carries a consent row and an active recruiter_starter
        subscription because both gates run BEFORE the ownership check:
        the consent gate would otherwise answer 403 CONSENT_REQUIRED, and
        recruiters on the free plan have zero match quota (tier_limits
        returns 402 PLAN_LIMIT_REACHED before the 404 is reachable).
        """
        jd_text = (
            "Buscamos Python developer con 5 años de experiencia en FastAPI, "
            "PostgreSQL y despliegues en AWS. Trabajo remoto, equipo pequeño."
        )

        async with clean_db.session_factory() as session:
            owner = User(
                email="roster_owner@test.com",
                password_hash="hashed",
                role="recruiter",
                full_name="Owner Recruiter",
            )
            attacker = User(
                email="roster_attacker@test.com",
                password_hash="hashed",
                role="recruiter",
                full_name="Attacker Recruiter",
            )
            session.add_all([owner, attacker])
            await session.commit()
            await session.refresh(owner)
            await session.refresh(attacker)

            # Consent gate (router + endpoint level) requires a consent row
            session.add(
                RecruiterConsent(
                    user_id=attacker.id,
                    accepted_at=datetime.now(UTC).replace(tzinfo=None),
                    tos_version="v1.2",
                )
            )
            # Tier check runs before the 404 path: free-plan recruiters have
            # 0 match quota, so the attacker needs an active paid plan
            session.add(
                Subscription(
                    user_id=attacker.id,
                    plan="recruiter_starter",
                    status="active",
                )
            )

            candidate = RecruiterCandidate(
                recruiter_id=owner.id,
                full_name="Foreign Candidate",
                email="foreign@example.com",
            )
            session.add(candidate)
            await session.commit()
            await session.refresh(candidate)
            foreign_candidate_id = candidate.id

        # Tier check + usage increment run via get_session_context (outside
        # DI): point it at the test DB like the patch_match_db fixture does
        factory = clean_db.session_factory

        @asynccontextmanager
        async def _session_context():
            async with factory() as session:
                yield session

        monkeypatch.setattr(
            recruiter_candidates_module, "get_session_context", _session_context
        )

        # Real JWT: the router-level verify_api_key guard calls
        # get_current_user() directly, bypassing dependency overrides
        token = create_access_token({"sub": str(attacker.id), "role": attacker.role})
        response = await async_client.post(
            f"/v1/recruiter/candidates/{foreign_candidate_id}/match",
            json={"jd_text": jd_text},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 404
        assert response.json()["detail"] == "CANDIDATE_NOT_FOUND"


# ---------------------------------------------------------------------------
# Issue #78 -- ``give_consent`` and ``get_consent`` must resolve the acting
# user from the JWT, never from a body field. The original bug declared
# ``current_user: CurrentUser`` (a plain dataclass) without ``Depends(...)``,
# so FastAPI treated it as a required body field and a real client sending
# only ``ConsentRequest`` got 422 -- masking the fact that the handler also
# read the acting identity out of a client-controlled body field. Once the
# 422 is fixed without fixing the identity, the handler creates rows for
# whoever the client claims to be.
# ---------------------------------------------------------------------------


def _seed_recruiter_user(clean_db, email: str) -> User:
    """Seed a recruiter and return it. Helper that ignores the test loop.

    The seeding path goes through ``clean_db.session_factory`` (the test
    SUPERUSER), so it bypasses RLS. The request path that follows uses a
    real JWT against the same DB.
    """

    async def _go() -> User:
        async with clean_db.session_factory() as session:
            u = User(
                email=email,
                password_hash="x",
                role="recruiter",
                full_name=email.split("@")[0].title(),
            )
            session.add(u)
            await session.commit()
            await session.refresh(u)
            session.expunge(u)
            return u

    return _go()


class TestConsentIdentityFromJWT:
    """``give_consent`` / ``get_consent`` resolve identity from the JWT.

    Two contracts pinned here:

    * The handler must NOT accept a ``current_user`` body field. The
      pre-fix endpoint declared ``current_user: CurrentUser`` with no
      ``Depends``, so FastAPI treated it as a required body field. The
      ``body==body`` regression test below shows the contract today: a
      ``ConsentRequest`` body alone (no ``current_user``) reaches the
      handler and the row is created for the **JWT** user.
    * When the body DOES carry a ``current_user`` payload, it is silently
      ignored. The pre-fix bug accepted that payload and used it as the
      acting principal, so a recruiter who sent ``current_user.id == 999``
      would mint a consent row for id 999 while RLS still bound the GUC to
      the JWT's user. The handler would then 500 on the foreign key, or --
      if 999 existed -- DANGER, persist a row for a different person than
      the JWT named. The ``body==ignored`` test pins the corrected behaviour:
      the row's ``user_id`` is the JWT user, not the body's.
    """

    async def test_give_consent_resolves_user_from_jwt_not_body(
        self, async_client, clean_db, override_get_session
    ):
        """The pre-fix bug took ``current_user.id`` from the body.

        The corrected handler ignores the body's ``current_user`` entirely
        and binds the row to the JWT subject. Sending a body that names
        user 999 while the JWT carries the recruiter must produce a row
        for the recruiter only, with no 5xx and no row for id 999.

        The body shape is the post-fix flat one (Pydantic silently drops
        ``current_user``), but the assertion below is the same as the
        pre-fix regression: the row's ``user_id`` must come from the JWT,
        not from any other source. If a future change reintroduces a
        ``current_user`` body field this test will still pass; the value
        of the test is in WHAT IT ASSERTS -- the JWT-side row -- not in
        how the impostor got into the payload.
        """
        recruiter = await _seed_recruiter_user(clean_db, "consent-jwt@test.com")
        token = create_access_token({"sub": str(recruiter.id), "role": recruiter.role})

        impostor_id = 999
        response = await async_client.post(
            "/v1/recruiter/consent",
            json={
                "accept_tos": True,
                "good_faith_declaration": True,
                "tos_version": "v1.2",
                # Pydantic drops this on the floor: ``ConsentRequest`` does
                # not declare ``current_user``. The point of including it
                # here is to prove the handler doesn't reach for it.
                "current_user": {
                    "id": impostor_id,
                    "name": "Impostor",
                    "role": "recruiter",
                    "auth_method": "jwt",
                },
            },
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 201, response.text
        assert response.json()["tos_version"] == "v1.2"

        # The DB row's user_id is the JWT's user, NOT the body's impostor.
        async with clean_db.session_factory() as session:
            for_uid = (
                await session.execute(
                    select(RecruiterConsent).where(
                        RecruiterConsent.user_id == recruiter.id
                    )
                )
            ).scalar_one_or_none()
            for_impostor = (
                await session.execute(
                    select(RecruiterConsent).where(
                        RecruiterConsent.user_id == impostor_id
                    )
                )
            ).scalar_one_or_none()

        assert for_uid is not None, "no consent row was created for the JWT user"
        assert for_uid.user_id == recruiter.id
        assert for_uid.tos_version == "v1.2"
        assert for_impostor is None, (
            "a consent row was created for the impostor id -- this is the "
            "pre-fix #78 identity divergence: the handler used a body field "
            f"as the acting principal instead of the JWT (impostor={impostor_id})"
        )

        # The audit log also names the JWT user, not the body's impostor.
        async with clean_db.session_factory() as session:
            audits = (
                (
                    await session.execute(
                        select(RecruiterAuditLog).where(
                            RecruiterAuditLog.action == "consent_given"
                        )
                    )
                )
                .scalars()
                .all()
            )

        assert audits, "no consent_given audit log was written"
        for row in audits:
            assert row.recruiter_id == recruiter.id, (
                f"audit row recruiter_id={row.recruiter_id} should be the JWT user "
                f"({recruiter.id}); pre-fix #78 would have written it from the "
                "body's current_user.id"
            )

    async def test_give_consent_rejects_when_no_jwt_is_present(
        self, async_client, clean_db
    ):
        """401 -- not 422. The handler must demand auth, not a body field.

        Pre-fix this would have 422'd asking for the ``current_user`` and
        ``body`` body fields, which masked the auth hole.
        """
        response = await async_client.post(
            "/v1/recruiter/consent",
            json={
                "accept_tos": True,
                "good_faith_declaration": True,
                "tos_version": "v1.2",
            },
        )

        assert response.status_code == 401, response.text
        assert response.json()["detail"] == "Invalid credentials"

    async def test_get_consent_resolves_user_from_jwt_not_body(
        self, async_client, clean_db, override_get_session
    ):
        """The same identity source for the read path.

        Pre-fix ``GET /v1/recruiter/consent`` also declared ``current_user:
        CurrentUser`` without ``Depends``. GETs typically have no body, but
        the bug only mattered if any code path could hand a different
        identity to the handler than the JWT. The corrected handler pulls
        from ``Depends(get_current_user)``, so even a stray body cannot
        redirect the read.
        """
        recruiter = await _seed_recruiter_user(clean_db, "consent-get@test.com")

        async with clean_db.session_factory() as session:
            session.add(
                RecruiterConsent(
                    user_id=recruiter.id,
                    accepted_at=datetime.now(UTC).replace(tzinfo=None),
                    tos_version="v1.2",
                )
            )
            await session.commit()

        token = create_access_token({"sub": str(recruiter.id), "role": recruiter.role})

        response = await async_client.get(
            "/v1/recruiter/consent",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200, response.text
        assert response.json()["tos_version"] == "v1.2"


# ---------------------------------------------------------------------------
# Issue #77 -- ``POST /v1/recruiter/candidates`` accepts the frontend's flat
# FormData shape (``client.ts:302-310``). The pre-fix endpoint declared
# ``body: CandidateCreate`` next to ``file: UploadFile = File(None)``, and on
# FastAPI 0.141.1 that combination yielded a multipart contract with a
# REQUIRED field literally named ``body``. Eight request shapes 422'd; this
# pair of tests pins the two that the frontend actually sends.
# ---------------------------------------------------------------------------


def _tiny_pdf_bytes(text: str) -> bytes:
    """A single-page PDF with extractable text. Copy of the helper in
    ``test_rls_commit_boundary.py`` -- private duplication to avoid turning
    a test helper into a cross-module import contract.
    """
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n"
        + stream + b"\nendstream",
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


class TestCreateCandidateMultipartContract:
    """Issue #77 -- the flat multipart shape the frontend sends must reach
    the handler. Pre-fix this 422'd because of a required ``body`` field on
    the contract.
    """

    async def _seed_recruiter_with_consent(self, clean_db, email: str) -> User:
        async with clean_db.session_factory() as session:
            u = User(
                email=email,
                password_hash="x",
                role="recruiter",
                full_name=email.split("@")[0].title(),
            )
            session.add(u)
            await session.commit()
            await session.refresh(u)
            session.expunge(u)

        async with clean_db.session_factory() as session:
            session.add(
                RecruiterConsent(
                    user_id=u.id,
                    accepted_at=datetime.now(UTC).replace(tzinfo=None),
                    tos_version="v1.2",
                )
            )
            await session.commit()
        return u

    async def test_post_candidate_multipart_flat_fields_creates_candidate(
        self, async_client, clean_db, override_get_session
    ):
        """Plain multipart with the four flat fields, no file. Must 201.

        Matches ``apiClient.createCandidate`` (``client.ts:302-310``) when
        the recruiter submits the form without attaching a PDF.
        """
        recruiter = await self._seed_recruiter_with_consent(
            clean_db, "cand-flat@test.com"
        )
        token = create_access_token({"sub": str(recruiter.id), "role": recruiter.role})

        response = await async_client.post(
            "/v1/recruiter/candidates",
            data={
                "full_name": "Ada Lovelace",
                "email": "ada-flat@example.com",
                "phone": "+54 11 5555 1234",
                "notes": "Frontend shape with no file",
            },
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 201, response.text
        body = response.json()
        assert body["full_name"] == "Ada Lovelace"
        assert body["email"] == "ada-flat@example.com"
        assert body["phone"] == "+54 11 5555 1234"
        assert body["notes"] == "Frontend shape with no file"
        assert body["cv_id"] is None
        assert body["recruiter_id"] == recruiter.id

    async def test_post_candidate_multipart_with_file_creates_candidate(
        self, async_client, clean_db, override_get_session
    ):
        """Multipart with the four flat fields PLUS a real PDF file. Must 201.

        Mirrors the frontend's ``apiClient.createCandidate`` call when the
        recruiter attaches a CV. The PDF must parse (50+ chars of text) so
        ``_parse_pdf_cv`` does not 503 on ``PDF_NO_TEXT``.
        """
        recruiter = await self._seed_recruiter_with_consent(
            clean_db, "cand-file@test.com"
        )
        token = create_access_token({"sub": str(recruiter.id), "role": recruiter.role})

        pdf_bytes = _tiny_pdf_bytes(
            "Grace Hopper. COBOL. Compiler pioneer. Forty years at the Navy."
        )

        response = await async_client.post(
            "/v1/recruiter/candidates",
            data={
                "full_name": "Grace Hopper",
                "email": "grace-file@example.com",
                "phone": None,
                "notes": "Frontend shape with file",
            },
            files={
                "file": (
                    "cv.pdf",
                    pdf_bytes,
                    "application/pdf",
                )
            },
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 201, response.text
        body = response.json()
        assert body["full_name"] == "Grace Hopper"
        assert body["email"] == "grace-file@example.com"
        assert body["cv_id"] is not None
        assert body["recruiter_id"] == recruiter.id

    async def test_post_candidate_rejects_when_no_jwt_is_present(
        self, async_client, clean_db
    ):
        """401 -- not 422. Without a JWT the handler must demand auth."""
        response = await async_client.post(
            "/v1/recruiter/candidates",
            data={"full_name": "Anon", "email": "anon@example.com"},
        )

        assert response.status_code == 401, response.text
