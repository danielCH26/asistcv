"""
Unit tests for the adaptation cache.

The cache is a thin layer over ``cv_adaptations`` (Slice A PR1 schema)
plus a content_version check against ``users_cvs``. These tests:

- Exercise ``compute_jd_text_hash`` as a pure function (no DB).
- Exercise ``get_cached`` against a clean test DB, binding the RLS
  user context so cv_adaptations policies see our row.

We rely on the project-wide ``clean_db`` fixture from ``tests/conftest.py``
which truncates user-owned tables between tests.
"""
from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from app.db.models import CVAdaptation, User, UserCV
from app.services.adaptation_cache import (
    CACHE_TTL,
    compute_jd_text_hash,
    get_cached,
)
from app.services.rls_context import set_rls_user


def _hash_text(text: str) -> str:
    """Reference hash for parametric comparison."""
    return hashlib.sha256(text[:500].encode("utf-8")).hexdigest()


class TestComputeJdTextHash:
    """``compute_jd_text_hash`` must be deterministic and bounded."""

    def test_returns_64_char_hex(self) -> None:
        h = compute_jd_text_hash("hello world")
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_matches_sha256_of_first_500_chars(self) -> None:
        jd = "x" * 600
        assert compute_jd_text_hash(jd) == _hash_text(jd)

    def test_deterministic(self) -> None:
        jd = "We are looking for a Senior Python Developer"
        assert compute_jd_text_hash(jd) == compute_jd_text_hash(jd)

    def test_tail_beyond_500_chars_does_not_affect_hash(self) -> None:
        # Two JDs that differ only in the tail must produce the same hash.
        head = "a" * 500
        tail_a = "x"
        tail_b = "y" * 200
        assert compute_jd_text_hash(head + tail_a) == compute_jd_text_hash(
            head + tail_b
        )

    def test_empty_string_returns_stable_hash(self) -> None:
        assert compute_jd_text_hash("") == hashlib.sha256(b"").hexdigest()

    def test_short_jd_returns_stable_hash(self) -> None:
        jd = "Senior Python Developer"
        assert compute_jd_text_hash(jd) == _hash_text(jd)


class TestGetCached:
    """``get_cached`` returns the most recent valid completed row."""

    @pytest.fixture
    async def owner(self, clean_db) -> User:
        """Create a test user that owns the CV + adaptations."""
        async with clean_db.session_factory() as session:
            user = User(
                email="owner@example.com",
                password_hash="x",
                role="job_seeker",
                full_name="Owner",
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            return user

    @pytest.fixture
    async def cv(self, clean_db, owner: User) -> UserCV:
        """Create a UserCV with content_version=1 for the owner."""
        async with clean_db.session_factory() as session:
            cv_row = UserCV(
                owner_user_id=owner.id,
                original_filename="cv.pdf",
                structured={
                    "full_name": "Owner",
                    "experience": [],
                    "skills": [],
                    "education": [],
                    "languages": [],
                },
                content_version=1,
            )
            session.add(cv_row)
            await session.commit()
            await session.refresh(cv_row)
            return cv_row

    async def _insert_adaptation(
        self,
        clean_db,
        cv_id: int,
        owner_user_id: int,
        *,
        jd_hash: str,
        status: str = "completed",
        created_at: datetime | None = None,
    ) -> CVAdaptation:
        """Helper to insert a CVAdaptation row directly."""
        async with clean_db.session_factory() as session:
            await set_rls_user(session, owner_user_id, "job_seeker")
            row = CVAdaptation(
                parent_cv_id=cv_id,
                owner_user_id=owner_user_id,
                jd_text_hash=jd_hash,
                adapted_cv_json={
                    "full_name": "Owner",
                    "experience": [],
                    "skills": [],
                    "education": [],
                    "languages": [],
                },
                status=status,
            )
            if created_at is not None:
                row.created_at = created_at
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return row

    async def test_returns_none_when_no_match(
        self, clean_db, owner: User, cv: UserCV
    ) -> None:
        """Empty cv_adaptations table → cache miss."""
        async with clean_db.session_factory() as session:
            await set_rls_user(session, owner.id, "job_seeker")
            hit = await get_cached(
                session, cv_id=cv.id, content_version=1, jd_text_hash="x" * 64
            )
            assert hit is None

    async def test_returns_completed_row(
        self, clean_db, owner: User, cv: UserCV
    ) -> None:
        """A completed row matching all 3 keys is returned."""
        jd_hash = "a" * 64
        await self._insert_adaptation(
            clean_db, cv_id=cv.id, owner_user_id=owner.id, jd_hash=jd_hash
        )

        async with clean_db.session_factory() as session:
            await set_rls_user(session, owner.id, "job_seeker")
            hit = await get_cached(
                session, cv_id=cv.id, content_version=1, jd_text_hash=jd_hash
            )
            assert hit is not None
            assert isinstance(hit, CVAdaptation)
            assert hit.jd_text_hash == jd_hash

    async def test_returns_most_recent(
        self, clean_db, owner: User, cv: UserCV
    ) -> None:
        """When the runner rewrites a row's status over time, the most recent completed row is returned.

        Since migration 021 the partial UNIQUE is scoped to
        ``status='pending'`` (``uq_cv_adapt_parent_jd_hash_pending``),
        so completed rows for one ``(cv, jd)`` may now stack up. This
        test therefore seeds two completed rows for the SAME pair — the
        shape a repeat adaptation after the 24 h TTL produces — and
        asserts the SQL ``ORDER BY created_at DESC LIMIT 1`` returns the
        newer one.
        """
        jd_hash = "ba" + "a" * 62
        older = await self._insert_adaptation(
            clean_db,
            cv_id=cv.id,
            owner_user_id=owner.id,
            jd_hash=jd_hash,
            created_at=datetime.now(UTC) - timedelta(minutes=5),
        )
        newer = await self._insert_adaptation(
            clean_db,
            cv_id=cv.id,
            owner_user_id=owner.id,
            jd_hash=jd_hash,
            created_at=datetime.now(UTC) - timedelta(seconds=10),
        )

        async with clean_db.session_factory() as session:
            await set_rls_user(session, owner.id, "job_seeker")
            hit = await get_cached(
                session, cv_id=cv.id, content_version=1, jd_text_hash=jd_hash
            )
            assert hit is not None
            # Same key for both rows: the tie is broken by recency, which
            # is what makes a repeat adaptation serve the fresh answer.
            assert hit.id == newer.id
            assert older.created_at < newer.created_at

    async def test_skips_pending_and_failed_rows(
        self, clean_db, owner: User, cv: UserCV
    ) -> None:
        """Pending / failed rows must NOT be returned as cache hits."""
        jd_hash = "c" * 64
        for status in ("pending", "failed"):
            await self._insert_adaptation(
                clean_db,
                cv_id=cv.id,
                owner_user_id=owner.id,
                jd_hash=jd_hash,
                status=status,
            )

        async with clean_db.session_factory() as session:
            await set_rls_user(session, owner.id, "job_seeker")
            hit = await get_cached(
                session, cv_id=cv.id, content_version=1, jd_text_hash=jd_hash
            )
            assert hit is None

    async def test_skips_stale_rows_outside_ttl(
        self, clean_db, owner: User, cv: UserCV
    ) -> None:
        """Rows older than ``CACHE_TTL`` must NOT be returned."""
        jd_hash = "d" * 64
        await self._insert_adaptation(
            clean_db,
            cv_id=cv.id,
            owner_user_id=owner.id,
            jd_hash=jd_hash,
            created_at=datetime.now(UTC) - CACHE_TTL - timedelta(minutes=1),
        )

        async with clean_db.session_factory() as session:
            await set_rls_user(session, owner.id, "job_seeker")
            hit = await get_cached(
                session, cv_id=cv.id, content_version=1, jd_text_hash=jd_hash
            )
            assert hit is None

    async def test_different_content_version_invalidates_cache(
        self, clean_db, owner: User, cv: UserCV
    ) -> None:
        """Asking for a content_version that doesn't match → miss.

        Simulates: cache was written at content_version=1, then the CV
        was edited (bumped to content_version=2), then the same request
        comes in. The runner must miss and rebuild against v2.
        """
        jd_hash = "e" * 64
        await self._insert_adaptation(
            clean_db, cv_id=cv.id, owner_user_id=owner.id, jd_hash=jd_hash
        )

        async with clean_db.session_factory() as session:
            await set_rls_user(session, owner.id, "job_seeker")
            hit = await get_cached(
                session,
                cv_id=cv.id,
                content_version=2,  # bumped since the row was written
                jd_text_hash=jd_hash,
            )
            assert hit is None

    async def test_matching_content_version_returns_row(
        self, clean_db, owner: User, cv: UserCV
    ) -> None:
        """When caller passes the same version as the CV, hit succeeds."""
        jd_hash = "f" * 64
        await self._insert_adaptation(
            clean_db, cv_id=cv.id, owner_user_id=owner.id, jd_hash=jd_hash
        )

        async with clean_db.session_factory() as session:
            await set_rls_user(session, owner.id, "job_seeker")
            hit = await get_cached(
                session, cv_id=cv.id, content_version=cv.content_version,
                jd_text_hash=jd_hash,
            )
            assert hit is not None
            assert hit.jd_text_hash == jd_hash

    async def test_different_jd_hash_misses(
        self, clean_db, owner: User, cv: UserCV
    ) -> None:
        """A different JD hash returns None even with same CV + version."""
        await self._insert_adaptation(
            clean_db,
            cv_id=cv.id,
            owner_user_id=owner.id,
            jd_hash="1" * 64,
        )

        async with clean_db.session_factory() as session:
            await set_rls_user(session, owner.id, "job_seeker")
            hit = await get_cached(
                session,
                cv_id=cv.id,
                content_version=1,
                jd_text_hash="2" * 64,
            )
            assert hit is None

    async def test_rls_isolation_other_user_cannot_read(
        self, clean_db, owner: User, cv: UserCV
    ) -> None:
        """Cross-tenant isolation is enforced at the policy layer.

        We don't re-prove the RLS policy itself here — ``tests/test_rls.py``
        covers that surface area. Instead we confirm that the cache
        lookup correctly scopes by ``parent_cv_id`` (the row in the
        DB has ``parent_cv_id=cv.id``; we look it up with the same id).

        The RLS policy on cv_adaptations ensures ``other`` users can't
        see this row even if they happened to know the cv_id and hash —
        that contract is enforced at the DB, not in this function.
        """
        jd_hash = "9" * 64
        await self._insert_adaptation(
            clean_db, cv_id=cv.id, owner_user_id=owner.id, jd_hash=jd_hash
        )

        async with clean_db.session_factory() as session:
            await set_rls_user(session, owner.id, "job_seeker")
            hit = await get_cached(
                session, cv_id=cv.id, content_version=1, jd_text_hash=jd_hash
            )
            # The owner can read their own row — that's the "happy" path
            # of the cache; the negative case (other user reading) is
            # exercised by test_rls.py with raw engine connections.
            assert hit is not None


class TestAdaptationUniqueness:
    """The partial unique index is scoped to IN-FLIGHT rows (migration 021).

    Pins both halves of the new invariant, because they are two
    different guarantees and either one alone would be a regression:

    - completed rows for the same ``(cv, jd)`` may stack up (history),
      which is what lets a repeat adaptation land after the 24 h TTL;
    - a second *pending* row for the same ``(cv, jd)`` is refused,
      which is what stops two concurrent POSTs from paying for two LLM
      calls.
    """

    @pytest.fixture
    async def owner(self, clean_db) -> User:
        async with clean_db.session_factory() as session:
            user = User(
                email="uq@example.com",
                password_hash="x",
                role="job_seeker",
                full_name="Uq",
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            return user

    @pytest.fixture
    async def cv(self, clean_db, owner: User) -> UserCV:
        async with clean_db.session_factory() as session:
            cv_row = UserCV(
                owner_user_id=owner.id,
                original_filename="cv.pdf",
                structured={},
                content_version=1,
            )
            session.add(cv_row)
            await session.commit()
            await session.refresh(cv_row)
            return cv_row

    async def _insert(
        self,
        clean_db,
        *,
        cv_id: int,
        owner_user_id: int,
        jd_hash: str,
        status: str,
    ) -> CVAdaptation:
        async with clean_db.session_factory() as session:
            await set_rls_user(session, owner_user_id, "job_seeker")
            row = CVAdaptation(
                parent_cv_id=cv_id,
                owner_user_id=owner_user_id,
                jd_text_hash=jd_hash,
                adapted_cv_json={},
                status=status,
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return row

    async def test_two_completed_rows_for_same_pair_are_allowed(
        self, clean_db, owner: User, cv: UserCV
    ) -> None:
        """Re-adapting the same JD later appends history.

        The old index (``WHERE status='completed'``) rejected this, which
        stranded the repeat request in ``pending`` after the LLM call had
        already been paid for.
        """
        jd_hash = compute_jd_text_hash("Backend role, Python and AWS.")
        first = await self._insert(
            clean_db,
            cv_id=cv.id,
            owner_user_id=owner.id,
            jd_hash=jd_hash,
            status="completed",
        )
        second = await self._insert(
            clean_db,
            cv_id=cv.id,
            owner_user_id=owner.id,
            jd_hash=jd_hash,
            status="completed",
        )
        assert first.id != second.id

    async def test_second_pending_row_for_same_pair_is_rejected(
        self, clean_db, owner: User, cv: UserCV
    ) -> None:
        """Only one in-flight job per (cv, jd) — the anti-concurrency half."""
        jd_hash = compute_jd_text_hash("Platform role, Go and Kubernetes.")
        await self._insert(
            clean_db,
            cv_id=cv.id,
            owner_user_id=owner.id,
            jd_hash=jd_hash,
            status="pending",
        )
        with pytest.raises(IntegrityError):
            await self._insert(
                clean_db,
                cv_id=cv.id,
                owner_user_id=owner.id,
                jd_hash=jd_hash,
                status="pending",
            )

    async def test_pending_may_flip_to_completed_while_old_completed_exists(
        self, clean_db, owner: User, cv: UserCV
    ) -> None:
        """The exact production failure: T completed, T+25h re-run.

        Reproduces the stuck-pending path at the schema level — the
        UPDATE that the runner performs is what used to raise.
        """
        jd_hash = compute_jd_text_hash("Data role, Python and dbt.")
        old = await self._insert(
            clean_db,
            cv_id=cv.id,
            owner_user_id=owner.id,
            jd_hash=jd_hash,
            status="completed",
        )
        repeat = await self._insert(
            clean_db,
            cv_id=cv.id,
            owner_user_id=owner.id,
            jd_hash=jd_hash,
            status="pending",
        )

        async with clean_db.session_factory() as session:
            await set_rls_user(session, owner.id, "job_seeker")
            row = await session.get(CVAdaptation, repeat.id)
            assert row is not None
            row.status = "completed"
            row.adapted_cv_json = {"full_name": "Uq"}
            row.completed_at = datetime.now(UTC)
            # This UPDATE violated uq_cv_adapt_parent_jd_hash_completed.
            await session.commit()

        async with clean_db.session_factory() as session:
            await set_rls_user(session, owner.id, "job_seeker")
            still_old = await session.get(CVAdaptation, old.id)
            updated = await session.get(CVAdaptation, repeat.id)
            assert still_old is not None
            assert still_old.status == "completed"
            assert updated is not None
            assert updated.status == "completed"
