"""
Mock LLM provider for local development and testing without GCP credentials.
"""
import hashlib
import json
from pathlib import Path
from typing import Any

from app.llm.schemas import (
    AdaptedCV,
    AdaptedExperienceItem,
    AuditIssue,
    CVAudit,
    Embedding,
    MatchAnalysis,
)

# Default response when no fixture matches
DEFAULT_RESPONSE = {
    "score": 65,
    "strengths": [
        "Relevant technical background",
        "Problem-solving skills demonstrated",
        "Team collaboration experience"
    ],
    "gaps": [
        "Specific domain experience needed",
        "Some technologies require ramp-up"
    ],
    "energy_level": "medium",
    "reasoning": "Candidate shows general fit with standard qualifications. Specific alignment with job requirements varies. Recommend detailed technical interview."
}


class MockProvider:
    """
    Deterministic mock LLM provider for development and testing.

    Uses fixture files for match responses and SHA256-based deterministic
    embeddings to ensure reproducible results.
    """

    def __init__(self, fixtures_dir: Path | None = None):
        """
        Initialize the mock provider.

        Args:
            fixtures_dir: Path to fixtures directory. Defaults to tests/fixtures/llm_responses
        """
        if fixtures_dir is None:
            # Default to the fixtures directory relative to backend
            # From app/llm/mock.py, go up to backend/ then into tests/fixtures
            fixtures_dir = Path(__file__).parent.parent.parent / "tests" / "fixtures" / "llm_responses"

        self.fixtures_dir = fixtures_dir
        self._fixtures: list[dict[str, Any]] = []
        self._load_fixtures()

    def _load_fixtures(self) -> None:
        """Load all fixture JSON files from the fixtures directory."""
        if not self.fixtures_dir.exists():
            return

        for fixture_file in sorted(self.fixtures_dir.glob("*.json")):
            try:
                with open(fixture_file, encoding="utf-8") as f:
                    self._fixtures.append(json.load(f))
            except (json.JSONDecodeError, OSError):
                # Skip invalid fixture files
                continue

    def _find_fixture_by_keywords(self, jd_text: str) -> dict[str, Any] | None:
        """
        Find a matching fixture based on keyword matching.

        If the JD text contains any keyword from a fixture, that fixture is returned.
        If multiple fixtures match, the first one (alphabetically sorted) is returned.

        Args:
            jd_text: The job description text to match

        Returns:
            The matching fixture response or None if no match
        """
        jd_lower = jd_text.lower()

        for fixture in self._fixtures:
            keywords = fixture.get("keywords", [])
            for keyword in keywords:
                if keyword.lower() in jd_lower:
                    return fixture.get("response")

        return None

    async def generate_match(
        self,
        jd_text: str,
        profile_context: dict[str, Any],
    ) -> MatchAnalysis:
        """
        Generate match analysis using fixture or default response.

        Args:
            jd_text: The job description text
            profile_context: Context information about the candidate

        Returns:
            MatchAnalysis with deterministic response
        """
        # Try to find a matching fixture by keywords
        response_data = self._find_fixture_by_keywords(jd_text)

        # Fall back to default if no fixture matches
        if response_data is None:
            response_data = DEFAULT_RESPONSE

        return MatchAnalysis(**response_data)

    async def generate_cv_audit(self, cv_text: str) -> CVAudit:
        """
        Generate a deterministic CV quality audit.

        Returns a fixed response so CV-only audits are reproducible in
        development and testing without external credentials.

        Args:
            cv_text: The CV text to audit

        Returns:
            CVAudit with deterministic score, problematicas, recomendaciones, fortalezas
        """
        return CVAudit(
            score=70,
            problematicas=[
                AuditIssue(
                    seccion="Experiencia",
                    problema="Logros sin cuantificar: no se detectan métricas ni resultados medibles",
                    severidad="high",
                ),
                AuditIssue(
                    seccion="Educación",
                    problema="Fechas inconsistentes o faltantes en la formación",
                    severidad="medium",
                ),
            ],
            recomendaciones=[
                "Cuantificá logros con números, porcentajes o alcance",
                "Verificá que las fechas de experiencia y educación sean consistentes",
            ],
            fortalezas=["Estructura general clara y legible"],
        )

    async def generate_adaptation(
        self,
        cv_structured: dict[str, Any],
        jd_text: str,
        *,
        max_tokens: int = 4000,
    ) -> AdaptedCV:
        """
        Generate a deterministic, validator-friendly adapted CV for local dev.

        Echoes the source CV verbatim and prepends a deterministic JD-keyword
        hint to each experience description. This keeps the honesty
        validator happy (every skill/company/description token comes from
        the source) while exercising the same code path as the real
        Groq-based flow.

        Args:
            cv_structured: Parsed CV in the same shape as ``UserCV.structured``.
            jd_text: Target job description (free text). Not used in the
                deterministic stub beyond extracting the first keyword.
            max_tokens: Ignored. Accepted to satisfy ``LLMProvider``.

        Returns:
            AdaptedCV echoing the source CV with a one-liner hint per
            experience bullet.
        """
        full_name = cv_structured.get("full_name", "")
        skills = list(cv_structured.get("skills", []))
        education = list(cv_structured.get("education", []))
        languages = list(cv_structured.get("languages", []))

        experience_blocks = []
        for exp in cv_structured.get("experience", []):
            title = exp.get("title", "")
            company = exp.get("company", "")
            dates = exp.get("dates", "")
            description = exp.get("description", "")
            # Inject a deterministic "highlight" that reuses words already
            # in the source — validator accepts (substring rule satisfied).
            highlight = f" [adapt note: aligned to JD ({title})]"
            experience_blocks.append(
                AdaptedExperienceItem(
                    title=title,
                    company=company,
                    dates=dates,
                    description=f"{description}{highlight}" if description else highlight.strip(),
                )
            )

        return AdaptedCV(
            full_name=full_name,
            experience=experience_blocks,
            skills=skills,
            education=education,
            languages=languages,
        )

    async def generate_embedding(self, text: str) -> Embedding:
        """
        Generate a deterministic embedding using SHA256 hash.

        The embedding is deterministic: same input always produces same output.
        Uses SHA256 to generate 32 bytes, then expands to 384 floats.
        Result is L2-normalized to have norm ≈ 1.0.

        Args:
            text: Input text to embed

        Returns:
            Embedding with 384-dimensional normalized vector
        """
        # Generate SHA256 hash of the text
        hash_bytes = hashlib.sha256(text.encode("utf-8")).digest()

        # Expand 32 bytes to 384 floats using a deterministic pattern
        # Each byte contributes to 12 float values (384 / 32 = 12)
        vector = []
        for byte_idx in range(32):
            byte_val = hash_bytes[byte_idx]
            for sub_idx in range(12):
                # Create deterministic float from byte
                base = (byte_val * 256 + sub_idx) / 65536.0
                vector.append(base)

        # Normalize to L2 norm = 1.0
        magnitude = sum(v * v for v in vector) ** 0.5
        if magnitude > 0:
            vector = [v / magnitude for v in vector]

        return Embedding(vector=vector, model="mock-embedding-v1")
