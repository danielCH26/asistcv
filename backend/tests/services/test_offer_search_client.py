"""
Tests for the offer search client (Tavily).
"""
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.services.offer_search_client import (
    OfferSearchAuthError,
    OfferSearchError,
    OfferSearchRateLimitError,
    OfferSearchResult,
    OfferSearchTimeoutError,
    TavilyOfferSearchClient,
)


class TestOfferSearchResult:
    """Tests for OfferSearchResult dataclass."""

    def test_result_with_all_fields(self):
        """Should hold all fields including published_date."""
        result = OfferSearchResult(
            title="Python Developer",
            url="https://example.com/job",
            snippet="Great opportunity for a Python developer",
            published_date="2024-01-15",
        )
        assert result.title == "Python Developer"
        assert result.url == "https://example.com/job"
        assert result.snippet == "Great opportunity for a Python developer"
        assert result.published_date == "2024-01-15"

    def test_result_with_null_published_date(self):
        """Should handle null published_date from Tavily."""
        result = OfferSearchResult(
            title="DevOps Engineer",
            url="https://example.com/devops",
            snippet="Looking for DevOps experience",
            published_date=None,
        )
        assert result.title == "DevOps Engineer"
        assert result.published_date is None


class TestTavilyOfferSearchClient:
    """Tests for TavilyOfferSearchClient."""

    @pytest.fixture
    def client(self) -> TavilyOfferSearchClient:
        """Create a client with test API key."""
        return TavilyOfferSearchClient(api_key="test_api_key_123")

    @pytest.mark.asyncio
    async def test_search_sends_post_with_api_key_in_body(self, client: TavilyOfferSearchClient):
        """Should send POST request with api_key in the request body."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "query": "python developer",
            "results": [
                {
                    "title": "Python Dev Job",
                    "url": "https://example.com/python",
                    "content": "Great Python role",
                    "score": 0.95,
                    "published_date": "2024-01-10",
                }
            ],
        }

        mock_post = AsyncMock(return_value=mock_response)

        with patch.object(httpx.AsyncClient, "post", mock_post):
            client._client = httpx.AsyncClient()
            result = await client.search("python developer")

        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args.kwargs
        assert call_kwargs["json"]["api_key"] == "test_api_key_123"
        assert call_kwargs["json"]["query"] == "python developer"
        assert call_kwargs["json"]["max_results"] == 10
        assert call_kwargs["json"]["search_depth"] == "basic"
        assert call_kwargs["json"]["include_answer"] is False
        assert result[0].title == "Python Dev Job"

    @pytest.mark.asyncio
    async def test_search_normalizes_results(self, client: TavilyOfferSearchClient):
        """Should normalize Tavily results to OfferSearchResult."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "query": "backend developer",
            "results": [
                {
                    "title": "Backend Engineer",
                    "url": "https://jobs.com/backend",
                    "content": "FastAPI experience preferred",
                    "score": 0.88,
                    "published_date": "2024-02-20",
                },
                {
                    "title": "Full Stack Role",
                    "url": "https://jobs.com/fullstack",
                    "content": "React + Node",
                    "score": 0.75,
                    "published_date": None,
                },
            ],
        }

        mock_post = AsyncMock(return_value=mock_response)

        with patch.object(httpx.AsyncClient, "post", mock_post):
            client._client = httpx.AsyncClient()
            results = await client.search("backend developer")

        assert len(results) == 2
        assert results[0].title == "Backend Engineer"
        assert results[0].url == "https://jobs.com/backend"
        assert results[0].snippet == "FastAPI experience preferred"
        assert results[0].published_date == "2024-02-20"
        assert results[1].title == "Full Stack Role"
        assert results[1].published_date is None

    @pytest.mark.asyncio
    async def test_search_without_api_key_raises_value_error(self):
        """Should raise ValueError when api_key is missing."""
        client = TavilyOfferSearchClient(api_key="")
        with pytest.raises(ValueError) as exc_info:
            await client.search("python developer")
        assert "TAVILY_API_KEY" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_search_401_raises_auth_error(self, client: TavilyOfferSearchClient):
        """Should raise OfferSearchAuthError on 401 response."""
        error_response = MagicMock()
        error_response.status_code = 401
        error_response.text = "Unauthorized"

        exc = httpx.HTTPStatusError(
            "401 Unauthorized",
            request=MagicMock(),
            response=error_response,
        )

        mock_post = AsyncMock(side_effect=exc)

        with patch.object(httpx.AsyncClient, "post", mock_post):
            client._client = httpx.AsyncClient()
            with pytest.raises(OfferSearchAuthError):
                await client.search("python developer")

    @pytest.mark.asyncio
    async def test_search_429_raises_rate_limit_error(self, client: TavilyOfferSearchClient):
        """Should raise OfferSearchRateLimitError on 429 response."""
        error_response = MagicMock()
        error_response.status_code = 429
        error_response.text = "Rate limit exceeded"
        error_response.headers = {"Retry-After": "60"}

        exc = httpx.HTTPStatusError(
            "429 Rate limit exceeded",
            request=MagicMock(),
            response=error_response,
        )

        mock_post = AsyncMock(side_effect=exc)

        with patch.object(httpx.AsyncClient, "post", mock_post):
            client._client = httpx.AsyncClient()
            with pytest.raises(OfferSearchRateLimitError) as exc_info:
                await client.search("python developer")
            assert exc_info.value.retry_after == 60

    @pytest.mark.asyncio
    async def test_search_429_without_retry_after(self, client: TavilyOfferSearchClient):
        """Should raise OfferSearchRateLimitError without retry_after if header absent."""
        error_response = MagicMock()
        error_response.status_code = 429
        error_response.text = "Rate limit exceeded"
        error_response.headers = {}

        exc = httpx.HTTPStatusError(
            "429 Rate limit exceeded",
            request=MagicMock(),
            response=error_response,
        )

        mock_post = AsyncMock(side_effect=exc)

        with patch.object(httpx.AsyncClient, "post", mock_post):
            client._client = httpx.AsyncClient()
            with pytest.raises(OfferSearchRateLimitError) as exc_info:
                await client.search("python developer")
            assert exc_info.value.retry_after is None

    @pytest.mark.asyncio
    async def test_search_500_raises_generic_error(self, client: TavilyOfferSearchClient):
        """Should raise OfferSearchError on 5xx responses."""
        error_response = MagicMock()
        error_response.status_code = 500
        error_response.text = "Internal server error"

        exc = httpx.HTTPStatusError(
            "500 Internal server error",
            request=MagicMock(),
            response=error_response,
        )

        mock_post = AsyncMock(side_effect=exc)

        with patch.object(httpx.AsyncClient, "post", mock_post):
            client._client = httpx.AsyncClient()
            with pytest.raises(OfferSearchError) as exc_info:
                await client.search("python developer")
            assert exc_info.value.status_code == 500
            assert "Internal server error" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_search_timeout_raises_timeout_error(self, client: TavilyOfferSearchClient):
        """Should raise OfferSearchTimeoutError on timeout."""
        mock_post = AsyncMock(side_effect=httpx.TimeoutException("timeout"))

        with patch.object(httpx.AsyncClient, "post", mock_post):
            client._client = httpx.AsyncClient()
            with pytest.raises(OfferSearchTimeoutError):
                await client.search("python developer")

    @pytest.mark.asyncio
    async def test_search_custom_max_results(self, client: TavilyOfferSearchClient):
        """Should respect custom max_results parameter."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"query": "test", "results": []}

        mock_post = AsyncMock(return_value=mock_response)

        with patch.object(httpx.AsyncClient, "post", mock_post):
            client._client = httpx.AsyncClient()
            await client.search("test query", max_results=5)

        call_kwargs = mock_post.call_args.kwargs
        assert call_kwargs["json"]["max_results"] == 5
