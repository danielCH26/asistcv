"""Ownership enforcement on `profiles` (issue #85, P0 IDOR).

The bug: `profiles` has NO row-level security (migration 011 never covered
it — `relrowsecurity = false`), and both `_get_profile_or_404` and the
profile lookup in `POST /v1/match` selected by `id` alone. Any
authenticated user could therefore read (and PATCH, and match against)
another user's profile, including the salary expectations inside
`preferences`.

Why these tests do NOT exercise RLS
-----------------------------------
`tests/conftest.py` installs a global `after_begin` listener that binds the
service RLS context (``app.current_user_id = '0'``) on every test
transaction, so every session here runs under the service bypass. That is
irrelevant to what is being asserted: `profiles` carries no RLS policies at
all, so no GUC value can change what a `SELECT` on it returns. Isolation in
these tests comes exclusively from the explicit service-level
``Profile.owner_user_id == <principal>`` predicate in the endpoint. Do not
read a pass here as evidence that RLS covers `profiles` — it does not.

Protected mode
--------------
Every test pins ``BACKEND_API_KEY`` so `optional_auth` resolves real JWT
principals instead of collapsing every caller to the service user (id 0).
In open mode there are no principals to tell apart, so the cross-user
assertions would be vacuous.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlmodel import select

import app.api.v1.match as match_module
from app.core.security import create_access_token
from app.db.models import Profile, User
from app.llm.schemas import Embedding, MatchAnalysis

API_KEY = "test-secret-key-abc123"

JD_TEXT = (
    "Buscamos Python developer con 5 años de experiencia en FastAPI, "
    "PostgreSQL y despliegues en AWS. Trabajo remoto, equipo pequeño."
)

EMBEDDING_MODEL = "BAAI/bge-m3"


def _make_provider() -> MagicMock:
    """Proveedor LLM mockeado: embeddings de 1024 + análisis válido."""
    provider = MagicMock(name="LLMProviderMock")
    provider.generate_embedding = AsyncMock(
        return_value=Embedding(
            vector=[0.1] * 384,
            model=EMBEDDING_MODEL,
            provider="huggingface",
        )
    )
    provider.generate_match = AsyncMock(
        return_value=MatchAnalysis(
            score=85,
            strengths=["Python", "FastAPI"],
            gaps=["Kubernetes"],
            energy_level="high",
            reasoning="Buen match general entre el perfil y el JD.",
        )
    )
    return provider


@pytest.fixture
def protected_mode(monkeypatch: pytest.MonkeyPatch):
    """Backend in protected mode: `optional_auth` resolves real principals.

    `get_settings` is lru_cached per process, so the cache is cleared on
    both sides of the change; otherwise the first request would keep
    seeing the open-mode configuration.
    """
    from app.core.config import get_settings

    monkeypatch.setenv("BACKEND_API_KEY", API_KEY)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def open_mode(monkeypatch: pytest.MonkeyPatch):
    """Backend in open mode: no BACKEND_API_KEY, so `optional_auth` fabricates
    the service user (id 0) for every caller.

    This is the mode in which the pre-fix endpoint actually minted orphan
    profiles: the router guard lets the request through and the handler
    never stamps an owner.
    """
    from app.core.config import get_settings

    monkeypatch.delenv("BACKEND_API_KEY", raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _jwt_header(user: User) -> dict[str, str]:
    token = create_access_token({"sub": str(user.id), "role": user.role})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def world(clean_db):
    """Two real job_seeker users, each owning one real profile.

    Seeded through the test session factory, which runs under the service
    RLS context (see the module docstring: `profiles` has no policies, so
    that context changes nothing here).
    """
    factory = clean_db.session_factory

    async with factory() as session:
        user_a = User(
            email="owner-a@test.com",
            password_hash="x",
            role="job_seeker",
            full_name="Alice",
        )
        user_b = User(
            email="owner-b@test.com",
            password_hash="x",
            role="job_seeker",
            full_name="Bob",
        )
        session.add_all([user_a, user_b])
        await session.flush()

        profile_a = Profile(
            name="Alice Profile",
            headline="Backend Engineer",
            experience={"years": 5},
            preferences={"salary_range": {"min": 120000, "max": 180000}},
            owner_user_id=user_a.id,
        )
        profile_b = Profile(
            name="Bob Profile",
            headline="Data Scientist",
            experience={"years": 8},
            preferences={"salary_range": {"min": 150000, "max": 220000}},
            owner_user_id=user_b.id,
        )
        session.add_all([profile_a, profile_b])
        await session.commit()
        await session.refresh(user_a)
        await session.refresh(user_b)
        await session.refresh(profile_a)
        await session.refresh(profile_b)

    return {
        "user_a": user_a,
        "user_b": user_b,
        "profile_a": profile_a,
        "profile_b": profile_b,
    }


async def _fetch_profile(clean_db, profile_id: int) -> Profile:
    async with clean_db.session_factory() as session:
        row = (
            await session.execute(select(Profile).where(Profile.id == profile_id))
        ).scalar_one_or_none()
        assert row is not None
        session.expunge(row)
        return row


# ---------------------------------------------------------------------------
# Cross-user denial: GET
# ---------------------------------------------------------------------------


async def test_user_a_cannot_get_user_b_profile(
    async_client, clean_db, override_get_session, protected_mode, world
):
    """A reading B's profile is 404, and B's salary range never leaks."""
    response = await async_client.get(
        f"/v1/profiles/{world['profile_b'].id}",
        headers=_jwt_header(world["user_a"]),
    )

    assert response.status_code == 404
    assert "150000" not in response.text
    assert "220000" not in response.text


async def test_user_a_cannot_get_user_b_embedding_status(
    async_client, clean_db, override_get_session, protected_mode, world
):
    """`/embedding-status` is the same lookup helper, so it is covered too."""
    response = await async_client.get(
        f"/v1/profiles/{world['profile_b'].id}/embedding-status",
        headers=_jwt_header(world["user_a"]),
    )

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Cross-user denial: PATCH (write path, the one that mutates rows)
# ---------------------------------------------------------------------------


async def test_user_a_cannot_patch_user_b_profile(
    async_client, clean_db, override_get_session, protected_mode, world
):
    """A cannot PATCH B's profile, and B's row is left byte-identical."""
    response = await async_client.patch(
        f"/v1/profiles/{world['profile_b'].id}",
        json={"name": "Pwned By Alice", "experience": {"years": 99}},
        headers=_jwt_header(world["user_a"]),
    )

    assert response.status_code == 404

    row = await _fetch_profile(clean_db, world["profile_b"].id)
    assert row.name == "Bob Profile"
    assert row.experience == {"years": 8}
    assert row.headline == "Data Scientist"
    assert row.preferences == {"salary_range": {"min": 150000, "max": 220000}}


# ---------------------------------------------------------------------------
# Cross-user denial: POST /v1/match
# ---------------------------------------------------------------------------


async def test_user_a_cannot_match_against_user_b_profile(
    async_client, clean_db, patch_match_db, protected_mode, world, monkeypatch
):
    """A cannot run a match on B's profile; the LLM never sees B's data."""
    provider = _make_provider()
    monkeypatch.setattr(match_module, "get_llm_provider", lambda: provider)

    response = await async_client.post(
        "/v1/match",
        json={"jd_text": JD_TEXT, "profile_id": world["profile_b"].id},
        headers=_jwt_header(world["user_a"]),
    )

    assert response.status_code == 404
    provider.generate_match.assert_not_called()


# ---------------------------------------------------------------------------
# POST /profiles must stamp ownership from a real principal
# ---------------------------------------------------------------------------


async def test_create_profile_without_auth_is_rejected(
    async_client, clean_db, override_get_session, patch_match_db, protected_mode
):
    """No credentials → rejected. It must not create an orphan row."""
    response = await async_client.post(
        "/v1/profiles",
        json={"name": "Anonymous Orphan"},
    )

    assert response.status_code in (401, 403)

    async with clean_db.session_factory() as session:
        orphans = (
            await session.execute(
                select(Profile).where(Profile.name == "Anonymous Orphan")
            )
        ).scalars().all()
    assert orphans == [], "unauthenticated POST must not persist a profile"


async def test_create_profile_in_open_mode_is_rejected(
    async_client, clean_db, override_get_session, patch_match_db, open_mode
):
    """Open mode: `optional_auth` yields service user 0, which owns nothing.

    Accepting here would mint exactly the orphan row the ownership filter
    then hides from everyone. A profile is an account-bound record, so
    creating one requires a real principal; there is no "anonymous profile"
    concept on this table.
    """
    response = await async_client.post(
        "/v1/profiles",
        json={"name": "Open Mode Orphan"},
    )

    assert response.status_code in (401, 403)

    async with clean_db.session_factory() as session:
        orphans = (
            await session.execute(
                select(Profile).where(Profile.name == "Open Mode Orphan")
            )
        ).scalars().all()
    assert orphans == [], "open mode must not persist an unowned profile"


async def test_create_profile_with_api_key_is_rejected(
    async_client, clean_db, override_get_session, patch_match_db, protected_mode
):
    """The service API key (id 0) is not an account: it cannot own a profile.

    `owner_user_id` has an FK to `users.id` and no user 0 exists, so
    stamping it would raise an IntegrityError (a 500) instead of a clean
    rejection.
    """
    response = await async_client.post(
        "/v1/profiles",
        json={"name": "Service Owned"},
        headers={"Authorization": f"Bearer {API_KEY}"},
    )

    assert response.status_code in (401, 403)

    async with clean_db.session_factory() as session:
        owned_by_service = (
            await session.execute(
                select(Profile).where(Profile.owner_user_id == 0)
            )
        ).scalars().all()
    assert owned_by_service == [], "a profile must never be owned by user 0"


async def test_create_profile_with_auth_stamps_owner(
    async_client, clean_db, override_get_session, patch_match_db, protected_mode,
    world, monkeypatch,
):
    """A JWT principal creates a profile owned by that principal."""
    monkeypatch.setattr(
        "app.api.v1.profiles.get_llm_provider", _make_provider
    )
    user_a = world["user_a"]

    response = await async_client.post(
        "/v1/profiles",
        json={"name": "Alice Fresh", "headline": "Staff Engineer"},
        headers=_jwt_header(user_a),
    )

    assert response.status_code == 201, response.text
    created_id = response.json()["id"]

    row = await _fetch_profile(clean_db, created_id)
    assert row.owner_user_id == user_a.id

    # And it is immediately readable by its owner.
    read_back = await async_client.get(
        f"/v1/profiles/{created_id}", headers=_jwt_header(user_a)
    )
    assert read_back.status_code == 200
    assert read_back.json()["name"] == "Alice Fresh"


# ---------------------------------------------------------------------------
# Legacy rows: owner_user_id IS NULL
# ---------------------------------------------------------------------------


async def test_null_owned_legacy_profile_is_invisible_to_real_users(
    async_client, clean_db, override_get_session, protected_mode, world
):
    """A pre-fix profile (owner NULL) must not be reachable by any user.

    This is the flip side of closing the hole: rows created before the fix
    have no owner, so the ownership predicate excludes them for everyone.
    Making them visible again is an explicit backfill decision (an
    operator action), never a silent fallback to "unowned = readable".
    """
    async with clean_db.session_factory() as session:
        legacy = Profile(name="Legacy Orphan", owner_user_id=None)
        session.add(legacy)
        await session.commit()
        await session.refresh(legacy)
        legacy_id = legacy.id

    for user in (world["user_a"], world["user_b"]):
        response = await async_client.get(
            f"/v1/profiles/{legacy_id}", headers=_jwt_header(user)
        )
        assert response.status_code == 404, f"legacy row leaked to {user.email}"


# ---------------------------------------------------------------------------
# Documented carve-out: the service principal keeps unfiltered read
# ---------------------------------------------------------------------------


async def test_service_principal_can_still_read_profiles(
    async_client, clean_db, override_get_session, protected_mode, world
):
    """API key (user 0) keeps MCP/single-user parity — see README note.

    `analyses.py` already grants the service principal unfiltered read for
    exactly this reason. This test pins that decision so a future change to
    it is a deliberate act, not an accident.
    """
    response = await async_client.get(
        f"/v1/profiles/{world['profile_b'].id}",
        headers={"Authorization": f"Bearer {API_KEY}"},
    )

    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Issue #87 — service-principal reads must be auditable (S2 + S3)
# ---------------------------------------------------------------------------


async def test_service_principal_read_emits_audit_log(
    async_client, clean_db, override_get_session, protected_mode, world, monkeypatch
):
    """Every API-key read of a profile emits a structured log line.

    The shared ``BACKEND_API_KEY`` is root of read over any profile (incl.
    salary range inside ``preferences``). Closing the leak is a bigger
    change; the minimum honest improvement is making every such read
    auditable. This test pins that contract.
    """
    from app.api.v1 import profiles as profiles_module

    captured: list[tuple[str, dict]] = []
    # structlog's ``info`` is bound by configure_logging; we patch the
    # module-level logger so the helper can swap in a recorder without
    # touching global log config.
    original_info = profiles_module.logger.info

    def recorder(event: str, **kwargs: object) -> None:
        captured.append((event, kwargs))

    monkeypatch.setattr(profiles_module.logger, "info", recorder)

    response = await async_client.get(
        f"/v1/profiles/{world['profile_b'].id}",
        headers={"Authorization": f"Bearer {API_KEY}"},
    )
    assert response.status_code == 200
    # Restore so the rest of the suite doesn't see a broken logger.
    monkeypatch.setattr(profiles_module.logger, "info", original_info)

    events = [c for c in captured if c[0] == "service_principal_profile_read"]
    assert events, f"Expected one service_principal_profile_read event, got: {captured}"
    event_name, payload = events[-1]
    assert payload["profile_id"] == world["profile_b"].id
    assert payload["auth_method"] == "api_key"


async def test_user_a_read_does_not_emit_service_audit_log(
    async_client, clean_db, override_get_session, protected_mode, world, monkeypatch
):
    """Real-JWT users reading their own profile must NOT emit the service log.

    The audit log is for the bypass path only. Normal user reads stay
    quiet (the standard access log is enough).
    """
    from app.api.v1 import profiles as profiles_module

    captured: list[str] = []
    original_info = profiles_module.logger.info

    def recorder(event: str, **kwargs: object) -> None:
        captured.append(event)

    monkeypatch.setattr(profiles_module.logger, "info", recorder)

    a = world["user_a"]
    response = await async_client.get(
        f"/v1/profiles/{world['profile_a'].id}",
        headers=_jwt_header(a),
    )
    assert response.status_code == 200
    monkeypatch.setattr(profiles_module.logger, "info", original_info)

    assert "service_principal_profile_read" not in captured


async def test_open_mode_service_principal_read_emits_log_with_auth_method_open(
    async_client, clean_db, override_get_session, open_mode, world, monkeypatch
):
    """In open mode (no BACKEND_API_KEY) the service user is auto-fabricated
    and the ownership filter is inerte. The audit log must still fire — and
    carry ``auth_method=open`` so it is distinguishable from a real
    API-key call. This is the dev-mode trace the issue (#87) called out.
    """
    from app.api.v1 import profiles as profiles_module

    captured: list[tuple[str, dict]] = []
    original_info = profiles_module.logger.info

    def recorder(event: str, **kwargs: object) -> None:
        captured.append((event, kwargs))

    monkeypatch.setattr(profiles_module.logger, "info", recorder)

    # No auth header at all — open mode fabricates the service user.
    response = await async_client.get(
        f"/v1/profiles/{world['profile_b'].id}"
    )
    assert response.status_code == 200
    monkeypatch.setattr(profiles_module.logger, "info", original_info)

    events = [c for c in captured if c[0] == "service_principal_profile_read"]
    assert events, f"Expected one service_principal_profile_read event, got: {captured}"
    event_name, payload = events[-1]
    assert payload["auth_method"] == "open"
    assert payload["profile_id"] == world["profile_b"].id


# ---------------------------------------------------------------------------
# Controls: the owner keeps full access
# ---------------------------------------------------------------------------


async def test_user_a_can_read_own_profile(
    async_client, clean_db, override_get_session, protected_mode, world
):
    """Control: ownership filtering must not break self-access."""
    response = await async_client.get(
        f"/v1/profiles/{world['profile_a'].id}",
        headers=_jwt_header(world["user_a"]),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == world["profile_a"].id
    assert body["name"] == "Alice Profile"
    assert body["preferences"]["salary_range"] == {"min": 120000, "max": 180000}


async def test_user_a_can_patch_own_profile(
    async_client, clean_db, override_get_session, protected_mode, world, monkeypatch
):
    """Control: the owner can still update their own profile."""
    monkeypatch.setattr("app.api.v1.profiles.get_llm_provider", _make_provider)

    response = await async_client.patch(
        f"/v1/profiles/{world['profile_a'].id}",
        json={"name": "Alice Updated"},
        headers=_jwt_header(world["user_a"]),
    )

    assert response.status_code == 200
    assert (await _fetch_profile(clean_db, world["profile_a"].id)).name == (
        "Alice Updated"
    )


async def test_user_a_can_match_against_own_profile(
    async_client, clean_db, patch_match_db, protected_mode, world, monkeypatch
):
    """Control: self-match still works end to end."""
    provider = _make_provider()
    monkeypatch.setattr(match_module, "get_llm_provider", lambda: provider)

    response = await async_client.post(
        "/v1/match",
        json={"jd_text": JD_TEXT, "profile_id": world["profile_a"].id},
        headers=_jwt_header(world["user_a"]),
    )

    assert response.status_code == 200, response.text
    assert response.json()["score"] == 85
    provider.generate_match.assert_awaited_once()


async def test_user_without_profile_match_returns_404(
    async_client, clean_db, patch_match_db, protected_mode, world, monkeypatch
):
    """A user who owns no profile at all gets 404, never someone else's.

    There is no auto-create on this endpoint: inventing one here would
    need its own ownership wiring, and the frontend already owns the
    create-on-demand path (`ensureProfile` in the profile page).
    """
    provider = _make_provider()
    monkeypatch.setattr(match_module, "get_llm_provider", lambda: provider)

    async with clean_db.session_factory() as session:
        stranger = User(
            email="stranger@test.com",
            password_hash="x",
            role="job_seeker",
            full_name="Stranger",
        )
        session.add(stranger)
        await session.commit()
        await session.refresh(stranger)

    response = await async_client.post(
        "/v1/match",
        json={"jd_text": JD_TEXT, "profile_id": world["profile_a"].id},
        headers=_jwt_header(stranger),
    )

    assert response.status_code == 404
    provider.generate_match.assert_not_called()
