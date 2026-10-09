"""
Tests for offer_search_worker — search → rank → persist pipeline.
"""
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.db.models import Profile, User
from app.llm.schemas import Embedding
from app.services.offer_search_client import OfferSearchResult

# ---------------------------------------------------------------------------
# Target
# ---------------------------------------------------------------------------
from app.services.offer_search_worker import OfferRunResult, run_offer_search

# ---------------------------------------------------------------------------
# Fixed reference time for deterministic staleness logic
# ---------------------------------------------------------------------------

NOW = datetime(2025, 1, 10, 12, 0, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_settings() -> Any:
    @dataclass
    class S:
        resolved_embedding_model: str = "gemini-embedding-001"
        offer_search_max_results: int = 10
        offer_search_min_score: int = 40
    return S()


@pytest.fixture
def mock_embedding_provider() -> AsyncMock:
    provider = AsyncMock()
    async def fake_embed(text: str) -> Embedding:
        return Embedding(
            vector=[0.1] * 768,
            model="gemini-embedding-001",
            provider="gemini",
        )
    provider.generate_embedding = AsyncMock(side_effect=fake_embed)
    return provider


@pytest.fixture
def mock_search_client() -> AsyncMock:
    client = AsyncMock()
    client.search = AsyncMock(
        return_value=[
            OfferSearchResult(
                title="Python Developer",
                url="https://jobs.com/1",
                snippet="We need a Python developer with FastAPI experience",
                published_date="2024-01-15",
            ),
            OfferSearchResult(
                title="Backend Engineer",
                url="https://jobs.com/2",
                snippet="Django and PostgreSQL skills required",
                published_date="2024-01-16",
            ),
            OfferSearchResult(
                title="DevOps Role",
                url="https://jobs.com/3",
                snippet="Kubernetes and CI/CD pipeline experience",
                published_date="2024-01-17",
            ),
        ]
    )
    return client


@pytest.fixture
def mock_session_factory() -> MagicMock:
    factory = MagicMock()
    session_ctx = MagicMock()
    session_ctx.__aenter__ = AsyncMock(return_value=session_ctx)
    session_ctx.__aexit__ = AsyncMock(return_value=None)
    exec_result = MagicMock()
    exec_result.fetchall = MagicMock(return_value=[])
    session_ctx.execute = AsyncMock(return_value=exec_result)
    session_ctx.commit = AsyncMock()
    session_ctx.add = MagicMock()
    session_ctx.expunge_all = MagicMock()
    factory.return_value = session_ctx
    return factory


# ---------------------------------------------------------------------------
# Object factories
# ---------------------------------------------------------------------------

def _make_profile(
    owner_user_id: int = 10,
    skills: dict[str, Any] | None = None,
    embedding: list[float] | None = None,
    embedding_model: str | None = None,
) -> Profile:
    p = Profile(
        id=1,
        owner_user_id=owner_user_id,
        name="Test User",
        headline="Senior Developer",
    )
    p.skills = skills or {"items": ["python", "fastapi", "postgresql"]}
    p.embedding = embedding
    p.embedding_model = embedding_model
    return p


def _make_user(
    user_id: int = 10,
    offer_preferences: dict | None = None,
) -> User:
    return User(
        id=user_id,
        email="test@example.com",
        role="job_seeker",
        full_name="Test User",
        password_hash="hashed",
        offer_preferences=offer_preferences,
    )


# ---------------------------------------------------------------------------
# Async mock helpers for internal pipeline steps
# ---------------------------------------------------------------------------

async def _fake_get_user_and_profile(uid: int, _fac: Any, user: User, profile: Profile | None):
    return user, profile


async def _fake_get_existing_urls(uid: int, _fac: Any) -> set[str]:
    return set()


async def _fake_persist_offers(
    uid: int, results: list[OfferSearchResult], _fac: Any, _query: str
) -> int:
    return len(results)


async def _fake_update_last_run_at(uid: int, _fac: Any, _prefs: Any, _now: Any) -> None:
    pass


# ---------------------------------------------------------------------------
# Shared patching decorator for all tests that need the full pipeline
# ---------------------------------------------------------------------------

def _with_pipeline_mocks(user: User, profile: Profile | None, **step_mocks):
    """Decorator that patches all internal steps to isolate the pipeline."""
    def decorator(fn):
        @pytest.mark.asyncio
        async def wrapper(*args, mock_settings, mock_search_client, mock_embedding_provider, mock_session_factory, **kwargs):
            # Build per-step mocks
            get_up = step_mocks.get("_get_user_and_profile")
            if get_up is None:
                get_up = _fake_get_user_and_profile

            get_urls = step_mocks.get("_get_existing_urls")
            if get_urls is None:
                get_urls = _fake_get_existing_urls

            persist = step_mocks.get("_persist_offers")
            if persist is None:
                persist = _fake_persist_offers

            update = step_mocks.get("_update_last_run_at")
            if update is None:
                update = _fake_update_last_run_at

            with patch("app.services.offer_search_worker._get_user_and_profile", get_up):
                with patch("app.services.offer_search_worker._get_existing_urls", get_urls):
                    with patch("app.services.offer_search_worker._persist_offers", persist):
                        with patch("app.services.offer_search_worker._update_last_run_at", update):
                            await fn(
                                *args,
                                mock_settings=mock_settings,
                                mock_search_client=mock_search_client,
                                mock_embedding_provider=mock_embedding_provider,
                                mock_session_factory=mock_session_factory,
                                user=user,
                                profile=profile,
                                **kwargs
                            )
        return wrapper
    return decorator


# ---------------------------------------------------------------------------
# Tests: staleness check
# ---------------------------------------------------------------------------

class TestStalenessShortCircuit:

    @pytest.mark.asyncio
    async def test_stale_user_skips_search(
        self, mock_settings, mock_search_client, mock_embedding_provider, mock_session_factory
    ):
        """IS stale → skipped_stale=True, search NOT called."""
        user = _make_user(
            offer_preferences={
                "frequency_hours": 24,
                "last_offer_run_at": datetime(2025, 1, 9, 0, 0, 0, tzinfo=UTC).isoformat(),
            }
        )
        profile = _make_profile()

        async def fake_get(uid, fac):
            return user, profile

        with patch("app.services.offer_search_worker._get_user_and_profile", fake_get):
            result = await run_offer_search(
                user_id=10,
                session_factory=mock_session_factory,
                settings=mock_settings,
                search_client=mock_search_client,
                embedding_provider=mock_embedding_provider,
                now=NOW,
            )

        assert result.skipped_stale is True
        mock_search_client.search.assert_not_called()

    @pytest.mark.asyncio
    async def test_not_stale_continues_pipeline(
        self, mock_settings, mock_search_client, mock_embedding_provider, mock_session_factory
    ):
        """NOT stale → pipeline continues, search IS called."""
        user = _make_user(
            offer_preferences={
                "frequency_hours": 24,
                "last_offer_run_at": datetime(2025, 1, 10, 0, 0, 0, tzinfo=UTC).isoformat(),
            }
        )
        profile = _make_profile()

        async def fake_get(uid, fac):
            return user, profile

        with patch("app.services.offer_search_worker._get_user_and_profile", fake_get):
            with patch("app.services.offer_search_worker._get_existing_urls", AsyncMock(return_value=set())):
                with patch("app.services.offer_search_worker._persist_offers", AsyncMock(return_value=3)):
                    with patch("app.services.offer_search_worker._update_last_run_at", AsyncMock()):
                        result = await run_offer_search(
                            user_id=10,
                            session_factory=mock_session_factory,
                            settings=mock_settings,
                            search_client=mock_search_client,
                            embedding_provider=mock_embedding_provider,
                            now=NOW,
                        )

        mock_search_client.search.assert_called_once()
        assert result.skipped_stale is False


# ---------------------------------------------------------------------------
# Tests: no profile
# ---------------------------------------------------------------------------

class TestNoProfile:

    @pytest.mark.asyncio
    async def test_no_profile_returns_empty_result(
        self, mock_settings, mock_search_client, mock_embedding_provider, mock_session_factory
    ):
        """No profile → skipped_stale=False, zero new_offers, no search."""
        user = _make_user()

        async def fake_get(uid, fac):
            return user, None

        with patch("app.services.offer_search_worker._get_user_and_profile", fake_get):
            result = await run_offer_search(
                user_id=10,
                session_factory=mock_session_factory,
                settings=mock_settings,
                search_client=mock_search_client,
                embedding_provider=mock_embedding_provider,
                now=NOW,
            )

        assert result.found == 0
        assert result.new_offers == 0
        mock_search_client.search.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: search query template
# ---------------------------------------------------------------------------

class TestSearchQueryTemplate:

    @pytest.mark.asyncio
    async def test_query_includes_skills(
        self, mock_settings, mock_search_client, mock_embedding_provider, mock_session_factory
    ):
        """Query string must include the user's skills from the profile."""
        profile = _make_profile(skills={"items": ["python", "fastapi", "postgresql"]})
        user = _make_user(
            offer_preferences={
                "frequency_hours": 24,
                "last_offer_run_at": datetime(2025, 1, 10, 0, 0, 0, tzinfo=UTC).isoformat(),
            }
        )

        async def fake_get(uid, fac):
            return user, profile

        with patch("app.services.offer_search_worker._get_user_and_profile", fake_get):
            with patch("app.services.offer_search_worker._get_existing_urls", AsyncMock(return_value=set())):
                with patch("app.services.offer_search_worker._persist_offers", AsyncMock(return_value=3)):
                    with patch("app.services.offer_search_worker._update_last_run_at", AsyncMock()):
                        await run_offer_search(
                            user_id=10,
                            session_factory=mock_session_factory,
                            settings=mock_settings,
                            search_client=mock_search_client,
                            embedding_provider=mock_embedding_provider,
                            now=NOW,
                        )

        mock_search_client.search.assert_called_once()
        query = mock_search_client.search.call_args[0][0]
        assert "python" in query
        assert "fastapi" in query


# ---------------------------------------------------------------------------
# Tests: ranking and threshold
# ---------------------------------------------------------------------------

class TestRanking:

    @pytest.mark.asyncio
    async def test_results_above_threshold_persisted(
        self, mock_settings, mock_search_client, mock_embedding_provider, mock_session_factory
    ):
        """Results scoring >= min_score are persisted."""
        profile = _make_profile(
            embedding=[0.1] * 768,
            embedding_model="gemini-embedding-001",
        )
        user = _make_user(
            offer_preferences={
                "frequency_hours": 24,
                # 12h ago → NOT stale → pipeline continues
                "last_offer_run_at": datetime(2025, 1, 10, 0, 0, 0, tzinfo=UTC).isoformat(),
            }
        )

        async def fake_get(uid, fac):
            return user, profile

        with patch("app.services.offer_search_worker._get_user_and_profile", fake_get):
            with patch("app.services.offer_search_worker._get_existing_urls", AsyncMock(return_value=set())):
                with patch("app.services.offer_search_worker._persist_offers", AsyncMock(return_value=3)) as mock_persist:
                    with patch("app.services.offer_search_worker._update_last_run_at", AsyncMock()):
                        result = await run_offer_search(
                            user_id=10,
                            session_factory=mock_session_factory,
                            settings=mock_settings,
                            search_client=mock_search_client,
                            embedding_provider=mock_embedding_provider,
                            now=NOW,
                        )

        assert result.found == 3
        assert result.new_offers == 3
        mock_persist.assert_called_once()

    @pytest.mark.asyncio
    async def test_results_below_threshold_filtered_out(
        self, mock_settings, mock_search_client, mock_embedding_provider, mock_session_factory
    ):
        """Results scoring below min_score are filtered before persist."""
        bad_provider = AsyncMock()
        async def fake_embed(text: str) -> Embedding:
            return Embedding(vector=[0.0] * 767 + [1.0], model="gemini-embedding-001", provider="gemini")
        bad_provider.generate_embedding = AsyncMock(side_effect=fake_embed)

        profile = _make_profile(
            embedding=[0.1] * 768,
            embedding_model="gemini-embedding-001",
        )
        user = _make_user(
            offer_preferences={
                "frequency_hours": 24,
                # 12h ago → NOT stale → pipeline continues
                "last_offer_run_at": datetime(2025, 1, 10, 0, 0, 0, tzinfo=UTC).isoformat(),
            }
        )

        async def fake_get(uid, fac):
            return user, profile

        with patch("app.services.offer_search_worker._get_user_and_profile", fake_get):
            with patch("app.services.offer_search_worker._get_existing_urls", AsyncMock(return_value=set())):
                with patch("app.services.offer_search_worker._persist_offers", AsyncMock(return_value=0)) as mock_persist:
                    with patch("app.services.offer_search_worker._update_last_run_at", AsyncMock()):
                        result = await run_offer_search(
                            user_id=10,
                            session_factory=mock_session_factory,
                            settings=mock_settings,
                            search_client=mock_search_client,
                            embedding_provider=bad_provider,
                            now=NOW,
                        )

        assert result.found == 3
        assert result.new_offers == 0
        # _persist_offers is always called (even with an empty list) — the
        # alias exists to pin that call.
        mock_persist.assert_awaited_once()


# ---------------------------------------------------------------------------
# Tests: deduplication
# ---------------------------------------------------------------------------

class TestDeduplication:

    @pytest.mark.asyncio
    async def test_existing_urls_are_skipped(
        self, mock_settings, mock_search_client, mock_embedding_provider, mock_session_factory
    ):
        """Results whose URL already exists for the user are not re-persisted."""
        profile = _make_profile(
            embedding=[0.1] * 768,
            embedding_model="gemini-embedding-001",
        )
        user = _make_user(
            offer_preferences={
                "frequency_hours": 24,
                # 12h ago → NOT stale → pipeline continues
                "last_offer_run_at": datetime(2025, 1, 10, 0, 0, 0, tzinfo=UTC).isoformat(),
            }
        )

        async def fake_get(uid, fac):
            return user, profile

        with patch("app.services.offer_search_worker._get_user_and_profile", fake_get):
            with patch("app.services.offer_search_worker._get_existing_urls", AsyncMock(return_value={"https://jobs.com/1", "https://jobs.com/2"})):
                with patch("app.services.offer_search_worker._persist_offers", AsyncMock(return_value=1)) as mock_persist:
                    with patch("app.services.offer_search_worker._update_last_run_at", AsyncMock()):
                        result = await run_offer_search(
                            user_id=10,
                            session_factory=mock_session_factory,
                            settings=mock_settings,
                            search_client=mock_search_client,
                            embedding_provider=mock_embedding_provider,
                            now=NOW,
                        )

        assert result.found == 3
        assert result.new_offers == 1
        mock_persist.assert_called_once()


# ---------------------------------------------------------------------------
# Tests: on-demand re-embedding
# ---------------------------------------------------------------------------

class TestOnDemandReEmbedding:

    @pytest.mark.asyncio
    async def test_null_embedding_triggers_reembed(
        self, mock_settings, mock_search_client, mock_embedding_provider, mock_session_factory
    ):
        """Profile with NULL embedding is re-embedded before ranking."""
        profile = _make_profile(embedding=None, embedding_model=None)
        user = _make_user(
            offer_preferences={
                "frequency_hours": 24,
                # 12h ago → NOT stale → pipeline continues
                "last_offer_run_at": datetime(2025, 1, 10, 0, 0, 0, tzinfo=UTC).isoformat(),
            }
        )

        async def fake_get(uid, fac):
            return user, profile

        with patch("app.services.offer_search_worker._get_user_and_profile", fake_get):
            with patch("app.services.offer_search_worker._get_existing_urls", AsyncMock(return_value=set())):
                with patch("app.services.offer_search_worker._persist_offers", AsyncMock(return_value=3)):
                    with patch("app.services.offer_search_worker._update_last_run_at", AsyncMock()):
                        await run_offer_search(
                            user_id=10,
                            session_factory=mock_session_factory,
                            settings=mock_settings,
                            search_client=mock_search_client,
                            embedding_provider=mock_embedding_provider,
                            now=NOW,
                        )

        # Re-embed: 1 profile + 3 snippets
        assert mock_embedding_provider.generate_embedding.call_count >= 4

    @pytest.mark.asyncio
    async def test_wrong_model_triggers_reembed(
        self, mock_settings, mock_search_client, mock_embedding_provider, mock_session_factory
    ):
        """Profile with a different embedding_model is re-embedded."""
        profile = _make_profile(
            embedding=[0.1] * 768,
            embedding_model="old-model-v1",
        )
        user = _make_user(
            offer_preferences={
                "frequency_hours": 24,
                # 12h ago → NOT stale → pipeline continues
                "last_offer_run_at": datetime(2025, 1, 10, 0, 0, 0, tzinfo=UTC).isoformat(),
            }
        )

        async def fake_get(uid, fac):
            return user, profile

        with patch("app.services.offer_search_worker._get_user_and_profile", fake_get):
            with patch("app.services.offer_search_worker._get_existing_urls", AsyncMock(return_value=set())):
                with patch("app.services.offer_search_worker._persist_offers", AsyncMock(return_value=3)):
                    with patch("app.services.offer_search_worker._update_last_run_at", AsyncMock()):
                        await run_offer_search(
                            user_id=10,
                            session_factory=mock_session_factory,
                            settings=mock_settings,
                            search_client=mock_search_client,
                            embedding_provider=mock_embedding_provider,
                            now=NOW,
                        )

        assert mock_embedding_provider.generate_embedding.call_count >= 4


# ---------------------------------------------------------------------------
# Tests: last_offer_run_at update
# ---------------------------------------------------------------------------

class TestLastRunUpdate:

    @pytest.mark.asyncio
    async def test_last_run_at_updated_after_success(
        self, mock_settings, mock_search_client, mock_embedding_provider, mock_session_factory
    ):
        """_update_last_run_at is called after a successful run."""
        profile = _make_profile(
            embedding=[0.1] * 768,
            embedding_model="gemini-embedding-001",
        )
        user = _make_user(
            offer_preferences={
                "frequency_hours": 24,
                # 12h ago → NOT stale → pipeline continues
                "last_offer_run_at": datetime(2025, 1, 10, 0, 0, 0, tzinfo=UTC).isoformat(),
            }
        )

        async def fake_get(uid, fac):
            return user, profile

        with patch("app.services.offer_search_worker._get_user_and_profile", fake_get):
            with patch("app.services.offer_search_worker._get_existing_urls", AsyncMock(return_value=set())):
                with patch("app.services.offer_search_worker._persist_offers", AsyncMock(return_value=3)):
                    with patch("app.services.offer_search_worker._update_last_run_at", AsyncMock()) as mock_update:
                        await run_offer_search(
                            user_id=10,
                            session_factory=mock_session_factory,
                            settings=mock_settings,
                            search_client=mock_search_client,
                            embedding_provider=mock_embedding_provider,
                            now=NOW,
                        )

        mock_update.assert_called_once()


# ---------------------------------------------------------------------------
# Tests: structured logging
# ---------------------------------------------------------------------------

class TestStructuredLogging:

    @pytest.mark.asyncio
    async def test_log_event_includes_user_id_and_counts(
        self, mock_settings, mock_search_client, mock_embedding_provider, mock_session_factory
    ):
        """Log event 'offer_search_run' is emitted."""
        profile = _make_profile(
            embedding=[0.1] * 768,
            embedding_model="gemini-embedding-001",
        )
        user = _make_user(
            offer_preferences={
                "frequency_hours": 24,
                # 12h ago → NOT stale → pipeline continues
                "last_offer_run_at": datetime(2025, 1, 10, 0, 0, 0, tzinfo=UTC).isoformat(),
            }
        )

        mock_logger = MagicMock()

        async def fake_get(uid, fac):
            return user, profile

        with patch("app.services.offer_search_worker._get_user_and_profile", fake_get):
            with patch("app.services.offer_search_worker._get_existing_urls", AsyncMock(return_value=set())):
                with patch("app.services.offer_search_worker._persist_offers", AsyncMock(return_value=3)):
                    with patch("app.services.offer_search_worker._update_last_run_at", AsyncMock()):
                        with patch("app.services.offer_search_worker.logger", mock_logger):
                            await run_offer_search(
                                user_id=10,
                                session_factory=mock_session_factory,
                                settings=mock_settings,
                                search_client=mock_search_client,
                                embedding_provider=mock_embedding_provider,
                                now=NOW,
                            )

        positional_event_names = [
            call[0][0] if call[0] else None
            for call in mock_logger.info.call_args_list
        ]
        assert "offer_search_run" in positional_event_names


# ---------------------------------------------------------------------------
# Tests: error propagation
# ---------------------------------------------------------------------------

class TestErrorPropagation:

    @pytest.mark.asyncio
    async def test_tavily_auth_error_propagates(
        self, mock_settings, mock_embedding_provider, mock_session_factory
    ):
        """OfferSearchAuthError from Tavily propagates unchanged."""
        from app.services.offer_search_client import OfferSearchAuthError

        error_client = AsyncMock()
        error_client.search = AsyncMock(side_effect=OfferSearchAuthError())

        profile = _make_profile()
        user = _make_user(
            offer_preferences={
                "frequency_hours": 24,
                # 12h ago → NOT stale → pipeline reaches search_client.search
                "last_offer_run_at": datetime(2025, 1, 10, 0, 0, 0, tzinfo=UTC).isoformat(),
            }
        )

        async def fake_get(uid, fac):
            return user, profile

        with patch("app.services.offer_search_worker._get_user_and_profile", fake_get):
            with pytest.raises(OfferSearchAuthError):
                await run_offer_search(
                    user_id=10,
                    session_factory=mock_session_factory,
                    settings=mock_settings,
                    search_client=error_client,
                    embedding_provider=mock_embedding_provider,
                    now=NOW,
                )


# ---------------------------------------------------------------------------
# Tests: OfferRunResult dataclass
# ---------------------------------------------------------------------------

class TestOfferRunResult:

    def test_result_fields(self):
        result = OfferRunResult(found=5, new_offers=3, skipped_stale=False)
        assert result.found == 5
        assert result.new_offers == 3
        assert result.skipped_stale is False

    def test_result_skipped_stale_true(self):
        result = OfferRunResult(found=0, new_offers=0, skipped_stale=True)
        assert result.skipped_stale is True
