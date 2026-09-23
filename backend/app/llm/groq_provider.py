"""
Groq provider implementation for LLM operations.

This provider uses the Groq API for match analysis generation.
Note: Groq does not offer embeddings - use HuggingFaceProvider for embeddings.
"""
import asyncio
import json
import logging
import time
from typing import Any, cast

import groq

from app.llm.schemas import Embedding, MatchAnalysis

logger = logging.getLogger(__name__)

# System prompt for match analysis
SYSTEM_PROMPT = """Eres un evaluador profesional de简历 vs descripciones de trabajo (JD).
Tu tarea es analizar qué tan bien un candidato califica para una posición específica.

## Reglas estrictas:
1. NO inventes skills que no estén en el perfil del candidato
2. Sé honesto - un score bajo es mejor que uno inflado falsamente
3. El tono debe ser profesional y objetivo
4. Responde ÚNICAMENTE con JSON válido, sin texto adicional

## Formato de salida (JSON):
{
  "score": 0-100,
  "strengths": ["lista de fortalezas que coinciden con el JD"],
  "gaps": ["lista de gaps o skills faltantes"],
  "energy_level": "low|medium|high",
  "reasoning": "explicación de 2-3 oraciones"
}

## Guidelines:
- score: 0-100 basado en match real
- energy_level: "low" (poco match), "medium" (buen match), "high" (excelente match)
- strengths: solo skills que aparecen tanto en JD como en el perfil
- gaps: solo requirements del JD que NO están en el perfil
"""

# User prompt template
USER_PROMPT_TEMPLATE = """## Job Description:
{jd_text}

## Candidate Profile:
{profile_context}

Evalúa el match y responde solo con JSON válido."""


class GroqProvider:
    """
    LLM provider using Groq API for match analysis.

    Note: This provider only implements generate_match.
    For embeddings, use HuggingFaceProvider.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "qwen/qwen3.8-27b",
        temperature: float = 0.3,
        max_tokens: int = 800,
    ):
        """
        Initialize the Groq provider.

        Args:
            api_key: Groq API key
            model: Model name to use (default: qwen/qwen3.8-27b)
            temperature: Sampling temperature (default: 0.3)
            max_tokens: Maximum tokens in response (default: 800)
        """
        self._client = groq.AsyncGroq(api_key=api_key)
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._max_retries = 2

    async def generate_match(
        self,
        jd_text: str,
        profile_context: dict[str, Any],
    ) -> MatchAnalysis:
        """
        Generate match analysis using Groq API.

        Args:
            jd_text: The job description text
            profile_context: Context information about the candidate

        Returns:
            MatchAnalysis with score, strengths, gaps, energy level, and reasoning
        """
        # Build the user prompt
        user_prompt = USER_PROMPT_TEMPLATE.format(
            jd_text=jd_text,
            profile_context=json.dumps(profile_context, indent=2),
        )

        start_time = time.time()
        last_error: Exception | None = None

        for attempt in range(self._max_retries + 1):
            try:
                response = await self._client.chat.completions.create(
                    model=self._model,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=self._temperature,
                    max_tokens=self._max_tokens,
                    response_format={"type": "json_object"},
                )

                latency = time.time() - start_time

                # Log tokens and latency
                usage = response.usage
                logger.info(
                    "Groq API call completed",
                    extra={
                        "model": self._model,
                        "latency_seconds": latency,
                        "prompt_tokens": usage.prompt_tokens if usage else None,
                        "completion_tokens": usage.completion_tokens if usage else None,
                        "total_tokens": usage.total_tokens if usage else None,
                    },
                )

                # Parse the response
                content = response.choices[0].message.content
                if not content:
                    raise ValueError("Empty response from Groq API")

                # Try to parse as JSON
                result = self._parse_json_response(content)

                return MatchAnalysis(**result)

            except groq.RateLimitError as e:
                last_error = e
                wait_time = 2**attempt  # Exponential backoff
                logger.warning(
                    "Groq rate limit hit, retrying",
                    extra={"attempt": attempt + 1, "wait_seconds": wait_time},
                )
                await asyncio.sleep(wait_time)

            except groq.APIConnectionError as e:
                last_error = e
                wait_time = 2**attempt
                logger.warning(
                    "Groq connection error, retrying",
                    extra={"attempt": attempt + 1, "wait_seconds": wait_time},
                )
                await asyncio.sleep(wait_time)

            except json.JSONDecodeError as e:
                # On first attempt, try with retry prompt
                if attempt == 0:
                    logger.warning("First JSON parse failed, retrying with explicit prompt")
                    user_prompt = (
                        user_prompt
                        + "\n\nIMPORTANTE: Responde ÚNICAMENTE con JSON válido. "
                        "No incluyas markdown, no incluyas texto adicional. "
                        "Solo el objeto JSON."
                    )
                    continue
                else:
                    raise ValueError(f"Failed to parse Groq response as JSON: {e}") from e

        # All retries exhausted
        raise last_error or RuntimeError("Groq API call failed after retries")

    def _parse_json_response(self, content: str) -> dict[str, Any]:
        """
        Parse JSON from Groq response, handling markdown code blocks.

        Args:
            content: Raw response content from Groq

        Returns:
            Parsed JSON as dictionary

        Raises:
            json.JSONDecodeError: If content is not valid JSON
        """
        # Strip markdown code blocks if present
        content = content.strip()
        if content.startswith("```json"):
            content = content[7:]
        elif content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]

        content = content.strip()

        return cast(dict[str, Any], json.loads(content))

    async def generate_embedding(self, text: str) -> Embedding:
        """
        Generate embedding is not supported by Groq.

        Args:
            text: Input text to embed

        Raises:
            NotImplementedError: Always, as Groq does not offer embeddings
        """
        raise NotImplementedError(
            "Groq does not offer embeddings. Use HuggingFaceProvider for embeddings."
        )
