"""
Tests for the Groq provider.
"""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.llm.groq_provider import GroqProvider


class TestGroqProvider:
    """Tests for the GroqProvider class."""

    @pytest.fixture
    def provider(self) -> GroqProvider:
        """Create a GroqProvider instance with test API key."""
        return GroqProvider(api_key="test_api_key", model="llama-3.3-70b-versatile")

    @pytest.mark.asyncio
    async def test_generate_match_returns_valid_analysis(self, provider: GroqProvider):
        """Should return valid MatchAnalysis from Groq response."""
        mock_response = {
            "score": 75,
            "strengths": ["Python", "FastAPI"],
            "gaps": ["AWS experience"],
            "energy_level": "high",
            "reasoning": "Good technical match with minor gaps.",
        }

        with patch.object(provider, "_client") as mock_client:
            mock_chat = AsyncMock()
            mock_completion = MagicMock()
            mock_completion.choices = [
                MagicMock(
                    message=MagicMock(content=json.dumps(mock_response)),
                )
            ]
            mock_completion.usage = MagicMock(
                prompt_tokens=100,
                completion_tokens=50,
                total_tokens=150,
            )
            mock_chat.completions.create = AsyncMock(return_value=mock_completion)
            mock_client.chat = mock_chat

            result = await provider.generate_match(
                jd_text="Senior Python developer",
                profile_context={"skills": ["Python", "FastAPI"]},
            )

            assert result.score == 75
            assert "Python" in result.strengths
            assert "AWS experience" in result.gaps
            assert result.energy_level == "high"

    @pytest.mark.asyncio
    async def test_generate_match_parses_markdown_json(self, provider: GroqProvider):
        """Should parse JSON wrapped in markdown code blocks."""
        mock_response = {
            "score": 80,
            "strengths": ["JavaScript"],
            "gaps": [],
            "energy_level": "medium",
            "reasoning": "Decent match.",
        }

        markdown_content = f"```json\n{json.dumps(mock_response)}\n```"

        with patch.object(provider, "_client") as mock_client:
            mock_chat = AsyncMock()
            mock_completion = MagicMock()
            mock_completion.choices = [
                MagicMock(message=MagicMock(content=markdown_content))
            ]
            mock_completion.usage = MagicMock(
                prompt_tokens=100,
                completion_tokens=50,
                total_tokens=150,
            )
            mock_chat.completions.create = AsyncMock(return_value=mock_completion)
            mock_client.chat = mock_chat

            result = await provider.generate_match(
                jd_text="JavaScript developer",
                profile_context={},
            )

            assert result.score == 80

    @pytest.mark.asyncio
    async def test_generate_embedding_raises_not_implemented(self, provider: GroqProvider):
        """Should raise NotImplementedError for embeddings."""
        with pytest.raises(NotImplementedError) as exc_info:
            await provider.generate_embedding("Some text")

        assert "Groq does not offer embeddings" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_generate_match_logs_token_usage(self, provider: GroqProvider):
        """Should log token usage after API call."""
        mock_response = {
            "score": 50,
            "strengths": [],
            "gaps": [],
            "energy_level": "medium",
            "reasoning": "Test",
        }

        with patch.object(provider, "_client") as mock_client:
            mock_chat = AsyncMock()
            mock_completion = MagicMock()
            mock_completion.choices = [
                MagicMock(message=MagicMock(content=json.dumps(mock_response)))
            ]
            mock_completion.usage = MagicMock(
                prompt_tokens=100,
                completion_tokens=50,
                total_tokens=150,
            )
            mock_chat.completions.create = AsyncMock(return_value=mock_completion)
            mock_client.chat = mock_chat

            with patch("app.llm.groq_provider.logger") as mock_logger:
                await provider.generate_match(jd_text="JD", profile_context={})

                mock_logger.info.assert_called()
                call_args = mock_logger.info.call_args
                assert "latency_seconds" in call_args.kwargs.get("extra", {})


class TestGroqProviderSystemPrompt:
    """Tests for the system prompt content."""

    def test_system_prompt_contains_json_instruction(self):
        """System prompt should instruct to return JSON only."""
        from app.llm.groq_provider import SYSTEM_PROMPT

        assert "JSON válido" in SYSTEM_PROMPT
        assert "sin texto adicional" in SYSTEM_PROMPT.lower()

    def test_system_prompt_contains_scoring_guidelines(self):
        """System prompt should contain scoring guidelines."""
        from app.llm.groq_provider import SYSTEM_PROMPT

        assert "score" in SYSTEM_PROMPT.lower()
        assert "energy_level" in SYSTEM_PROMPT

    def test_user_prompt_template_accepts_variables(self):
        """User prompt template should format correctly."""
        from app.llm.groq_provider import USER_PROMPT_TEMPLATE

        result = USER_PROMPT_TEMPLATE.format(
            jd_text="Python developer",
            profile_context='{"skills": ["Python"]}',
        )

        assert "Python developer" in result
        assert "skills" in result


class TestGroqProviderFactory:
    """Tests for Groq provider integration with factory."""

    def test_factory_requires_groq_api_key(self):
        """Should raise error if GROQ_API_KEY is missing."""
        from app.llm.factory import get_llm_provider

        with patch("app.llm.factory.get_settings") as mock_settings:
            mock_settings.return_value.llm_provider = "groq"
            mock_settings.return_value.groq_api_key = None
            mock_settings.return_value.huggingface_api_key = "hf_token"

            get_llm_provider.cache_clear()

            with pytest.raises(ValueError) as exc_info:
                get_llm_provider()

            assert "GROQ_API_KEY" in str(exc_info.value)

            get_llm_provider.cache_clear()

    def test_factory_requires_huggingface_api_key_for_groq(self):
        """Should raise error if HUGGINGFACE_API_KEY is missing for groq mode."""
        from app.llm.factory import get_llm_provider

        with patch("app.llm.factory.get_settings") as mock_settings:
            mock_settings.return_value.llm_provider = "groq"
            mock_settings.return_value.groq_api_key = "groq_key"
            mock_settings.return_value.huggingface_api_key = None

            get_llm_provider.cache_clear()

            with pytest.raises(ValueError) as exc_info:
                get_llm_provider()

            assert "HUGGINGFACE_API_KEY" in str(exc_info.value)

            get_llm_provider.cache_clear()
