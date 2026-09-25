"""
Database-level RLS isolation tests (migration 011, Sprint 2 PR6).

These tests assert isolation AT THE DATABASE, not at the endpoint: they
run raw SQL through the app's engine with an explicit
``app.current_user_id`` GUC (the same mechanism the API binds per
request via app.services.rls_context). Endpoint-level tests at the end
prove the FastAPI wiring (404, never 403 — no existence leak).

Bypass mechanism under test: GUC '0' = service (MCP adapter, cron
cleanup, Stripe webhook). GUC 'anonymous' = free-audit funnel for
unlinked audit_uploads rows.
"""
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import status
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection

from app.api.deps import CurrentUser, optional_auth
from app.core.security import create_access_token
from app.db.models import (
    Analysis,
    AuditUpload,
    JobDescription,
    RecruiterCandidate,
    RecruiterCandidateCV,
    RecruiterConsent,
    Subscription,
    User,
    UserCV,
)
from app.main import app
from tests.conftest import RLS_TEST_ROLE

# Tables protected by migration 011 (used by the no-GUC default-deny test)
_PROTECTED_TABLES = (
    "users_cvs",
    "analyses",
    "recruiter_candidates",
    "recruiter_candidates_cvs",
    "recruiter_analyses",
    "recruiter_consents",
    "subscriptions",
    "payments",
    "usage_counters",
    "audit_uploads",
)


@asynccontextmanager
async def conn_as(engine, user_id: str | None) -> AsyncConnection:
    """Connection acting as the non-superuser app role, with an explicit
    RLS GUC (None = no GUC at all).

    The docker/CI test user is a superuser, and superusers bypass RLS
    even with FORCE — so every RLS assertion runs under SET ROLE with a
    NOBYPASSRLS role that owns the tables (same as the production app
    user on Neon).
    """
    async with engine.connect() as conn:
        await conn.execute(text(f"SET ROLE {RLS_TEST_ROLE}"))
        # Commit so the session-level SET ROLE survives any later
        # transaction rollback inside the test (a rollback reverts SET
        # ROLE executed within the same transaction).
        await conn.commit()
        if user_id is not None:
            await conn.execute(
                text(f"SET LOCAL app.current_user_id = '{user_id}'")  # noqa: S608
            )
        yield conn


async def _fetch_ids(conn: AsyncConnection, sql: str) -> set[int]:
    result = await conn.execute(text(sql))
    return {row[0] for row in result.fetchall()}


async def _count(conn: AsyncConnection, table: str) -> int:
    result = await conn.execute(text(f"SELECT COUNT(*) FROM {table}"))  # noqa: S608
    return int(result.scalar_one())


def _jwt_header(user_id: int, role: str) -> dict[str, str]:
    token = create_access_token({"sub": str(user_id), "role": role})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def world(clean_db):
    """Two job_seekers, two recruiters (with consent), and one row each.

    Everything is seeded through the test session factory, which runs
    under the service RLS context (bypass '0') — same as MCP/provisioning
    paths in production.
    """
    factory = clean_db.session_factory
    ids: dict[str, int] = {}

    async with factory() as session:
        user_a = User(
            email="rls-a@test.com", password_hash="x", role="job_seeker", full_name="A"
        )
        user_b = User(
            email="rls-b@test.com", password_hash="x", role="job_seeker", full_name="B"
        )
        rec1 = User(
            email="rls-r1@test.com", password_hash="x", role="recruiter", full_name="R1"
        )
        rec2 = User(
            email="rls-r2@test.com", password_hash="x", role="recruiter", full_name="R2"
        )
        session.add_all([user_a, user_b, rec1, rec2])
        await session.flush()

        for user in (rec1, rec2):
            session.add(
                RecruiterConsent(
                    user_id=user.id,
                    accepted_at=datetime.now(UTC).replace(tzinfo=None),
                    tos_version="v1.2",
                )
            )

        session.add(UserCV(
            owner_user_id=user_a.id,
            original_filename="a.pdf",
            structured={"full_name": "A"},
        ))
        session.add(UserCV(
            owner_user_id=user_b.id,
            original_filename="b.pdf",
            structured={"full_name": "B"},
        ))

        jd = JobDescription(raw_text="JD " * 40)
        session.add(jd)
        await session.flush()

        session.add(Analysis(
            job_description_id=jd.id, owner_user_id=user_a.id, score=60
        ))
        session.add(Analysis(
            job_description_id=jd.id, owner_user_id=user_b.id, score=70
        ))

        for user, filename in ((rec1, "r1.pdf"), (rec2, "r2.pdf")):
            cv = RecruiterCandidateCV(original_filename=filename)
            session.add(cv)
            await session.flush()
            session.add(RecruiterCandidate(
                recruiter_id=user.id, full_name=f"Cand {filename}", cv_id=cv.id
            ))

        sub = Subscription(user_id=user_a.id, plan="free", status="active")
        session.add(sub)
        await session.flush()

        # Backfill candidate_id on the CV children (same flow as the
        # endpoint: cv flushed first, then linked to its candidate).
        links = (await session.execute(
            select(RecruiterCandidate.id, RecruiterCandidate.cv_id)
        )).all()
        for candidate_id, cv_id in links:
            if cv_id is not None:
                await session.execute(
                    update(RecruiterCandidateCV)
                    .where(RecruiterCandidateCV.id == cv_id)
                    .values(candidate_id=candidate_id)
                )

        await session.commit()

        ids.update(
            user_a=user_a.id,
            user_b=user_b.id,
            recruiter1=rec1.id,
            recruiter2=rec2.id,
            job_description=jd.id,
            subscription=sub.id,
        )

    # Re-read ids of rows created without explicit handles
    async with factory() as session:
        cvs = (await session.execute(
            select(UserCV.original_filename, UserCV.id)
        )).all()
        filename_to_id = {filename: cv_id for filename, cv_id in cvs}
        ids["cv_a"] = filename_to_id["a.pdf"]
        ids["cv_b"] = filename_to_id["b.pdf"]

        analyses = (await session.execute(
            select(Analysis.id, Analysis.score)
        )).all()
        ids["analysis_a"] = next(i for i, s in analyses if s == 60)
        ids["analysis_b"] = next(i for i, s in analyses if s == 70)

        candidates = (await session.execute(
            select(RecruiterCandidate.id, RecruiterCandidate.full_name)
        )).all()
        ids["candidate_1"] = next(i for i, n in candidates if "r1" in n)
        ids["candidate_2"] = next(i for i, n in candidates if "r2" in n)

        child_cvs = (await session.execute(
            select(RecruiterCandidateCV.id, RecruiterCandidateCV.original_filename)
        )).all()
        ids["rcv_1"] = next(i for i, fn in child_cvs if fn == "r1.pdf")
        ids["rcv_2"] = next(i for i, fn in child_cvs if fn == "r2.pdf")

    return ids


class TestDatabaseLevelIsolation:
    """RLS filters rows at the engine level, per app.current_user_id."""

    async def test_user_cannot_select_other_users_cv(self, clean_db, world):
        async with conn_as(clean_db.engine, str(world["user_a"])) as conn:
            seen = await _fetch_ids(conn, "SELECT id FROM users_cvs")
        assert seen == {world["cv_a"]}

        async with conn_as(clean_db.engine, str(world["user_b"])) as conn:
            seen = await _fetch_ids(conn, "SELECT id FROM users_cvs")
        assert seen == {world["cv_b"]}

        async with conn_as(clean_db.engine, str(world["user_b"])) as conn:
            leak = await _fetch_ids(
                conn, f"SELECT id FROM users_cvs WHERE id = {world['cv_a']}"
            )
        assert leak == set()

    async def test_user_cannot_select_other_users_analyses(self, clean_db, world):
        async with conn_as(clean_db.engine, str(world["user_a"])) as conn:
            seen = await _fetch_ids(conn, "SELECT id FROM analyses")
        assert seen == {world["analysis_a"]}

        async with conn_as(clean_db.engine, str(world["user_b"])) as conn:
            leak = await _fetch_ids(
                conn, f"SELECT id FROM analyses WHERE id = {world['analysis_a']}"
            )
        assert leak == set()

    async def test_cross_user_insert_is_blocked(self, clean_db, world):
        # WITH CHECK rejects inserting a row owned by someone else. Each
        # attempt gets its own connection: the raised violation aborts the
        # transaction, and the discarded connection frees it.
        async with conn_as(clean_db.engine, str(world["user_a"])) as conn:
            with pytest.raises(DBAPIError):
                await conn.execute(text(
                    f"INSERT INTO users_cvs (owner_user_id, original_filename, structured) "
                    f"VALUES ({world['user_b']}, 'evil.pdf', '{{}}')"
                ))

        async with conn_as(clean_db.engine, str(world["user_a"])) as conn:
            with pytest.raises(DBAPIError):
                await conn.execute(text(
                    f"INSERT INTO analyses (job_description_id, owner_user_id) "
                    f"VALUES ({world['job_description']}, {world['user_b']})"
                ))

    async def test_recruiter_cannot_select_other_recruiters_candidates(
        self, clean_db, world
    ):
        async with conn_as(clean_db.engine, str(world["recruiter1"])) as conn:
            seen = await _fetch_ids(conn, "SELECT id FROM recruiter_candidates")
        assert seen == {world["candidate_1"]}

        async with conn_as(clean_db.engine, str(world["recruiter2"])) as conn:
            leak = await _fetch_ids(
                conn,
                f"SELECT id FROM recruiter_candidates WHERE id = {world['candidate_1']}",
            )
        assert leak == set()

    async def test_recruiter_candidate_cvs_follow_parent(self, clean_db, world):
        async with conn_as(clean_db.engine, str(world["recruiter1"])) as conn:
            seen = await _fetch_ids(conn, "SELECT id FROM recruiter_candidates_cvs")
        assert world["rcv_1"] in seen
        assert world["rcv_2"] not in seen

        async with conn_as(clean_db.engine, str(world["recruiter2"])) as conn:
            leak = await _fetch_ids(
                conn,
                f"SELECT id FROM recruiter_candidates_cvs WHERE id = {world['rcv_1']}",
            )
        assert leak == set()

    async def test_cross_role_isolation(self, clean_db, world):
        # A recruiter must see zero job_seeker CVs...
        async with conn_as(clean_db.engine, str(world["recruiter1"])) as conn:
            assert await _count(conn, "users_cvs") == 0
        # ...and a job_seeker must see zero recruiter candidates.
        async with conn_as(clean_db.engine, str(world["user_a"])) as conn:
            assert await _count(conn, "recruiter_candidates") == 0

    async def test_owner_can_update_and_delete_own_rows(self, clean_db, world):
        # Positive control: owners keep full CRUD on their own rows.
        async with conn_as(clean_db.engine, str(world["user_a"])) as conn:
            result = await conn.execute(text(
                f"UPDATE users_cvs SET original_filename = 'a2.pdf' "
                f"WHERE id = {world['cv_a']}"
            ))
            assert result.rowcount == 1

        async with conn_as(clean_db.engine, str(world["user_a"])) as conn:
            result = await conn.execute(text(
                f"DELETE FROM analyses WHERE id = {world['analysis_a']}"
            ))
            assert result.rowcount == 1


class TestServiceBypass:
    """GUC '0' is the single service bypass (MCP adapter + cron paths)."""

    async def test_service_user_reads_across_users(self, clean_db, world):
        async with conn_as(clean_db.engine, "0") as conn:
            cv_ids = await _fetch_ids(conn, "SELECT id FROM users_cvs")
            analysis_ids = await _fetch_ids(conn, "SELECT id FROM analyses")
            candidate_ids = await _fetch_ids(
                conn, "SELECT id FROM recruiter_candidates"
            )
            subscription_ids = await _fetch_ids(conn, "SELECT id FROM subscriptions")

        assert {world["cv_a"], world["cv_b"]} <= cv_ids
        assert {world["analysis_a"], world["analysis_b"]} <= analysis_ids
        assert {world["candidate_1"], world["candidate_2"]} <= candidate_ids
        assert {world["subscription"]} <= subscription_ids

    async def test_cron_bypass_deletes_only_expired_unlinked_audits(
        self, clean_db, world
    ):
        factory = clean_db.session_factory
        now = datetime.now(UTC)
        async with factory() as session:
            expired_unlinked = AuditUpload(
                audit_token_hash="expired_unlinked", jd_text="j",
                expires_at=now - timedelta(days=1),
            )
            fresh_unlinked = AuditUpload(
                audit_token_hash="fresh_unlinked", jd_text="j",
                expires_at=now + timedelta(days=30),
            )
            expired_linked = AuditUpload(
                audit_token_hash="expired_linked", jd_text="j",
                expires_at=now - timedelta(days=1),
                linked_user_id=world["user_a"],
            )
            session.add_all([expired_unlinked, fresh_unlinked, expired_linked])
            await session.commit()
            world["audit_expired_unlinked"] = expired_unlinked.id
            world["audit_fresh_unlinked"] = fresh_unlinked.id
            world["audit_expired_linked"] = expired_linked.id

        # Cron-style delete, exactly like audit_retention.delete_expired_audits
        async with conn_as(clean_db.engine, "0") as conn:
            result = await conn.execute(text(
                "DELETE FROM audit_uploads "
                "WHERE linked_user_id IS NULL AND expires_at < NOW() "
                "RETURNING audit_token_hash"
            ))
            deleted = {row[0] for row in result.fetchall()}
            await conn.commit()
        assert "expired_unlinked" in deleted
        assert "fresh_unlinked" not in deleted
        assert "expired_linked" not in deleted

        # The linked (claimed) and fresh rows survive
        async with conn_as(clean_db.engine, "0") as conn:
            remaining = await _fetch_ids(
                conn, "SELECT id FROM audit_uploads"
            )
        assert world["audit_expired_linked"] in remaining
        assert world["audit_fresh_unlinked"] in remaining
        assert world["audit_expired_unlinked"] not in remaining

    async def test_no_guc_sees_nothing_and_cannot_insert(self, clean_db, world):
        """FORCE RLS proof: no context at all → zero rows, inserts rejected."""
        async with conn_as(clean_db.engine, None) as conn:
            for table in _PROTECTED_TABLES:
                assert await _count(conn, table) == 0, table

        async with conn_as(clean_db.engine, None) as conn:
            with pytest.raises(DBAPIError):
                await conn.execute(text(
                    f"INSERT INTO users_cvs (owner_user_id, original_filename, structured) "
                    f"VALUES ({world['user_a']}, 'x.pdf', '{{}}')"
                ))


class TestAnonymousAuditFlow:
    """Free-audit funnel: 'anonymous' context owns unlinked rows only."""

    async def test_anonymous_write_and_readback(self, clean_db, world):
        async with conn_as(clean_db.engine, "anonymous") as conn:
            result = await conn.execute(text(
                "INSERT INTO audit_uploads (audit_token_hash, jd_text, expires_at) "
                "VALUES ('anon_tok_1', 'anonymous audit', NOW() + INTERVAL '30 days') "
                "RETURNING id"
            ))
            audit_id = result.scalar_one()

            readback = await _fetch_ids(
                conn, f"SELECT id FROM audit_uploads WHERE id = {audit_id}"
            )
        assert readback == {audit_id}

    async def test_anonymous_cannot_read_linked_rows(self, clean_db, world):
        factory = clean_db.session_factory
        async with factory() as session:
            linked = AuditUpload(
                audit_token_hash="linked_tok", jd_text="j",
                expires_at=datetime.now(UTC) + timedelta(days=1),
                linked_user_id=world["user_a"],
            )
            session.add(linked)
            await session.commit()
            world["audit_linked"] = linked.id

        # Anonymous sees only unlinked rows; the linked one is invisible...
        async with conn_as(clean_db.engine, "anonymous") as conn:
            leak = await _fetch_ids(
                conn, f"SELECT id FROM audit_uploads WHERE id = {linked.id}"
            )
        assert leak == set()

        # ...while its owner sees exactly that row.
        async with conn_as(clean_db.engine, str(world["user_a"])) as conn:
            seen = await _fetch_ids(
                conn, f"SELECT id FROM audit_uploads WHERE id = {linked.id}"
            )
        assert seen == {linked.id}

        # Anonymous cannot link a row to a user either (WITH CHECK rejects
        # the transition inside the same transaction).
        async with conn_as(clean_db.engine, "anonymous") as conn:
            result = await conn.execute(text(
                "INSERT INTO audit_uploads (audit_token_hash, jd_text, expires_at) "
                "VALUES ('anon_tok_2', 'j', NOW() + INTERVAL '30 days') "
                "RETURNING id"
            ))
            audit_id = result.scalar_one()

            with pytest.raises(DBAPIError):
                await conn.execute(text(
                    f"UPDATE audit_uploads SET linked_user_id = {world['user_b']} "
                    f"WHERE id = {audit_id}"
                ))


# === Endpoint-level wiring (RLS GUC bound per request by get_db) ===


class TestEndpointIsolation:
    """Cross-user endpoint access returns 404 (never 403 — no existence leak)."""

    @pytest.fixture
    def override_principal(self):
        installed: dict = {}

        def _install(dependency, principal):
            app.dependency_overrides[dependency] = lambda: principal
            installed[dependency] = True

        yield _install
        for dependency in installed:
            app.dependency_overrides.pop(dependency, None)

    async def test_get_other_users_cv_returns_404(self, clean_db, world):
        # Real JWT wiring: router guard + get_current_user + get_db all
        # resolve user A, and the GUC is bound to A.id for the query.
        headers = _jwt_header(world["user_a"], "job_seeker")
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            own = await ac.get(f"/v1/cvs/{world['cv_a']}", headers=headers)
            other = await ac.get(f"/v1/cvs/{world['cv_b']}", headers=headers)

        assert own.status_code == status.HTTP_200_OK
        assert other.status_code == status.HTTP_404_NOT_FOUND

    async def test_get_other_users_analysis_returns_404(
        self, clean_db, world, override_principal
    ):
        # optional_auth ignores JWTs in open mode, so bind the principal
        # via the dependency the endpoint's get_db_optional consumes.
        override_principal(
            optional_auth,
            CurrentUser(
                id=world["user_a"], name="A", role="job_seeker", auth_method="jwt"
            ),
        )
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            own = await ac.get(f"/v1/analyses/{world['analysis_a']}")
            other = await ac.get(f"/v1/analyses/{world['analysis_b']}")

        assert own.status_code == status.HTTP_200_OK
        assert other.status_code == status.HTTP_404_NOT_FOUND

    async def test_get_other_recruiters_candidate_returns_404(self, clean_db, world):
        # Real JWT: verify_api_key + consent gate + get_db all bind R1.
        headers = _jwt_header(world["recruiter1"], "recruiter")
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            own = await ac.get(
                f"/v1/recruiter/candidates/{world['candidate_1']}", headers=headers
            )
            other = await ac.get(
                f"/v1/recruiter/candidates/{world['candidate_2']}", headers=headers
            )

        assert own.status_code == status.HTTP_200_OK
        assert other.status_code == status.HTTP_404_NOT_FOUND
