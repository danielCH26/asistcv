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

from app.llm.schemas import AdaptedCV, CVAudit, Embedding, MatchAnalysis

logger = logging.getLogger(__name__)

# Default token budget for adaptation calls (a full CV rewrite needs more
# headroom than the 800-token match/audit flow).
ADAPTATION_DEFAULT_MAX_TOKENS = 4000

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

# System prompt for CV quality audit (no JD involved)
CV_AUDIT_SYSTEM_PROMPT = """Eres un auditor profesional de hojas de vida (CVs).
Tu tarea es evaluar la calidad de un CV por sí solo, sin compararlo con ninguna vacante.

## Reglas estrictas:
1. Basate ÚNICAMENTE en el texto del CV provisto
2. Sé honesto - un score bajo es mejor que uno inflado falsamente
3. El tono debe ser profesional y objetivo
4. Responde ÚNICAMENTE con JSON válido, sin texto adicional

## Formato de salida (JSON):
{
  "score": 0-100,
  "problematicas": [
    {"seccion": "sección del CV", "problema": "descripción del problema", "severidad": "low|medium|high"}
  ],
  "recomendaciones": ["acciones concretas para mejorar el CV"],
  "fortalezas": ["puntos fuertes del CV"]
}

## Verificaciones:
- Secciones faltantes (contacto, experiencia, educación, skills)
- Logros sin cuantificar (sin números, porcentajes o métricas)
- Verbos débiles o genéricos
- Longitud inadecuada (muy corto o demasiado extenso)
- Fechas inconsistentes o faltantes
- Redundancia de contenido
"""

# User prompt template for CV quality audit
CV_AUDIT_USER_PROMPT_TEMPLATE = """## CV del candidato:
{cv_text}

Evalúa la calidad del CV y responde solo con JSON válido."""

# System prompt for CV -> JD adaptation (Slice A, PR2).
# Honesty contract: the model may REWRITE bullets but may not INVENT
# facts. The validator downstream enforces the substring rule; this
# prompt makes the contract explicit so the model self-rejects drift.
CV_ADAPTATION_SYSTEM_PROMPT = """Eres un asistente que adapta CVs a ofertas de trabajo. REGLAS ESTRICTAS:
1. SOLO puedes usar contenido presente en el CV fuente. NO inventes habilidades, trabajos, fechas, ni logros.
2. Reescribe los bullets de experiencia para resaltar relevancia al JD. NO agregues experiencia nueva.
3. Output JSON estricto con la estructura: {"full_name": str, "experience": [{"title": str, "company": str, "dates": str, "description": str}], "skills": list[str], "education": list[dict], "languages": list[str]}.
4. La lista de skills DEBE ser un subset del CV fuente. NO agregues skills nuevas.
5. Responde ÚNICAMENTE con JSON válido, sin markdown ni texto adicional."""

# User prompt template for CV -> JD adaptation.
CV_ADAPTATION_USER_PROMPT_TEMPLATE = """CV fuente (JSON):
{cv_json}

JD objetivo:
{jd_text}

Genera el CV adaptado. Solo JSON válido, sin texto adicional."""


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
        user_prompt = USER_PROMPT_TEMPLATE.format(
            jd_text=jd_text,
            profile_context=json.dumps(profile_context, indent=2),
        )

        result = await self._complete_json(SYSTEM_PROMPT, user_prompt)
        return MatchAnalysis(**result)

    async def generate_cv_audit(self, cv_text: str) -> CVAudit:
        """
        Generate a CV quality audit using Groq API.

        Args:
            cv_text: The CV text to audit

        Returns:
            CVAudit with score, problematicas, recomendaciones, and fortalezas
        """
        user_prompt = CV_AUDIT_USER_PROMPT_TEMPLATE.format(cv_text=cv_text)

        result = await self._complete_json(CV_AUDIT_SYSTEM_PROMPT, user_prompt)
        return CVAudit(**result)

    async def generate_adaptation(
        self,
        cv_structured: dict[str, Any],
        jd_text: str,
        *,
        max_tokens: int = ADAPTATION_DEFAULT_MAX_TOKENS,
    ) -> AdaptedCV:
        """
        Adapt a structured CV to a target job description.

        Implements the Slice A contract: rewrite ``experience[*].description``
        bullets to highlight JD relevance while keeping every fact verbatim
        from the source. The honesty guarantee is enforced downstream by
        ``adaptation_validator``; this provider just emits the JSON shape.

        Args:
            cv_structured: Parsed CV in the same shape as
                ``UserCV.structured``.
            jd_text: Target job description (free text).
            max_tokens: Per-call response token cap. Defaults to
                ``ADAPTATION_DEFAULT_MAX_TOKENS`` (4000); raised above
                the match/audit default because adapted CVs are longer.

        Returns:
            AdaptedCV instance matching the LLM-emitted JSON.
        """
        user_prompt = CV_ADAPTATION_USER_PROMPT_TEMPLATE.format(
            cv_json=json.dumps(cv_structured, indent=2, ensure_ascii=False),
            jd_text=jd_text,
        )

        result = await self._complete_json(
            CV_ADAPTATION_SYSTEM_PROMPT,
            user_prompt,
            max_tokens=max_tokens,
        )
        return AdaptedCV(**result)

    async def _complete_json(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        """
        Run a JSON-mode chat completion with retries and robust JSON parsing.

        Shared by generate_match and generate_cv_audit: exponential backoff on
        rate limit/connection errors, one explicit-JSON retry on parse failure,
        ValueError when the response never becomes valid JSON.

        Args:
            system_prompt: System message content
            user_prompt: User message content
            max_tokens: Per-call override for the response token cap. When
                ``None`` (default), falls back to ``self._max_tokens`` set
                in the constructor (matches prior behavior for match/audit).

        Returns:
            Parsed JSON response as a dictionary
        """
        start_time = time.time()
        last_error: Exception | None = None
        effective_max_tokens = self._max_tokens if max_tokens is None else max_tokens

        for attempt in range(self._max_retries + 1):
            try:
                response = await self._client.chat.completions.create(
                    model=self._model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=self._temperature,
                    max_tokens=effective_max_tokens,
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
                return self._parse_json_response(content)

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
