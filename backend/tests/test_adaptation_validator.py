"""
Unit tests for the adaptation honesty validator.

The validator is the no-honesty-violation gate between the LLM and the
persisted adapted CV. These tests exercise the normalizer, the
substring matching rules, and the per-section checks (skills,
companies, experience metadata, descriptions).

We do NOT touch the DB here — the validator is a pure function over
the source/adapted dicts. This keeps the test suite fast and avoids
the conftest DB setup overhead for what is essentially a string
comparison pipeline.
"""
from __future__ import annotations

import pytest

from app.services.adaptation_validator import (
    ValidationResult,
    normalize,
    validate_adaptation,
)

# === normalize() ===


class TestNormalize:
    """``normalize`` is the foundation of substring matching."""

    def test_lowercases(self) -> None:
        assert normalize("Python") == "python"
        assert normalize("JAVA") == "java"

    def test_strips_punctuation(self) -> None:
        # Dots, dashes, slashes, middle-dot separators all collapse.
        assert normalize("Node.js") == "nodejs"
        assert normalize("cross-platform") == "crossplatform"
        assert normalize("CI/CD") == "cicd"

    def test_preserves_abbreviations(self) -> None:
        # ``ReactJS`` stays ``reactjs`` — the ``s`` is part of ``JS``,
        # not a plural. (Earlier revisions stripped trailing ``s`` and
        # produced ``reactj``; that regression is locked against here.)
        assert normalize("ReactJS") == "reactjs"

    def test_strips_diacritics(self) -> None:
        assert normalize("Diseño") == "diseno"
        assert normalize("Gestión") == "gestion"
        assert normalize("Múltiples") == "multiples"

    def test_collapses_whitespace(self) -> None:
        assert normalize("  Python  ") == "python"
        assert normalize("a\tb\nc") == "a b c"

    def test_empty_inputs(self) -> None:
        assert normalize("") == ""
        assert normalize(None or "") == ""  # type: ignore[arg-type]

    def test_pure_punctuation_returns_empty(self) -> None:
        assert normalize("...") == ""
        assert normalize("---") == ""

    def test_unicode_normalization_combined(self) -> None:
        # Diacritics + uppercase + extra whitespace all collapse together.
        assert normalize("  Años  ") == "anos"
        assert normalize("Ingeniería") == "ingenieria"


# === validate_adaptation() happy path ===


class TestValidateAdaptationHappyPath:
    """Honest adaptations — no invented facts — must pass."""

    def test_identical_cv_is_valid(self) -> None:
        """An exact copy of the source (no rewriting) must validate."""
        source = {
            "full_name": "Jane Doe",
            "experience": [
                {
                    "title": "Senior Backend Engineer",
                    "company": "Acme",
                    "dates": "2020-2024",
                    "description": "Built Python services on AWS.",
                }
            ],
            "skills": ["Python", "AWS", "PostgreSQL"],
            "education": [],
            "languages": ["English"],
        }
        result = validate_adaptation(source, source)
        assert result.ok is True
        assert result.violations == []

    def test_skills_subset_of_source(self) -> None:
        """Adapted skills that are a subset of source skills validate."""
        source = {
            "full_name": "Jane Doe",
            "experience": [
                {
                    "title": "Engineer",
                    "company": "Acme",
                    "dates": "2020-2024",
                    "description": "Built things.",
                }
            ],
            "skills": ["Python", "AWS", "PostgreSQL", "Docker"],
            "education": [],
            "languages": [],
        }
        adapted = dict(source)
        adapted["skills"] = ["Python", "AWS"]
        result = validate_adaptation(source, adapted)
        assert result.ok is True

    def test_substring_match_after_normalization(self) -> None:
        """``ReactJS`` in adapted matches ``React`` in source after normalize."""
        source = {
            "full_name": "Jane",
            "experience": [
                {
                    "title": "Engineer",
                    "company": "Acme",
                    "dates": "2020-2024",
                    "description": "Worked with React for two years.",
                }
            ],
            "skills": ["React", "Python"],
            "education": [],
            "languages": [],
        }
        adapted = dict(source)
        adapted["skills"] = ["ReactJS", "Python"]
        result = validate_adaptation(source, adapted)
        assert result.ok is True, result.violations

    def test_rewritten_description_with_source_tokens(self) -> None:
        """Adapted description that only reuses source tokens validates."""
        source = {
            "full_name": "Jane",
            "experience": [
                {
                    "title": "Engineer",
                    "company": "Acme",
                    "dates": "2020-2024",
                    "description": "Built Python microservices on AWS Lambda. Led team of 5.",
                }
            ],
            "skills": ["Python", "AWS"],
            "education": [],
            "languages": [],
        }
        adapted = {
            "full_name": "Jane",
            "experience": [
                {
                    "title": "Engineer",
                    "company": "Acme",
                    "dates": "2020-2024",
                    # Only reuses tokens present in the source description.
                    "description": "Built Python microservices. AWS Lambda. Led team of 5.",
                }
            ],
            "skills": ["Python", "AWS"],
            "education": [],
            "languages": [],
        }
        result = validate_adaptation(source, adapted)
        assert result.ok is True, result.violations

    def test_date_ranges_preserved(self) -> None:
        """Date ranges copied verbatim from source pass."""
        source = {
            "full_name": "Jane",
            "experience": [
                {
                    "title": "Engineer",
                    "company": "Acme",
                    "dates": "Jan 2020 - Dec 2024",
                    "description": "Worked.",
                }
            ],
            "skills": [],
            "education": [],
            "languages": [],
        }
        adapted = dict(source)
        result = validate_adaptation(source, adapted)
        assert result.ok is True


# === validate_adaptation() rejection paths ===


class TestValidateAdaptationRejections:
    """Adapted CVs with invented content must fail loudly."""

    def test_invented_skill_rejected(self) -> None:
        """A skill not present in source triggers a violation."""
        source = {
            "full_name": "Jane",
            "experience": [
                {
                    "title": "Engineer",
                    "company": "Acme",
                    "dates": "2020-2024",
                    "description": "Built Python services.",
                }
            ],
            "skills": ["Python"],
            "education": [],
            "languages": [],
        }
        adapted = dict(source)
        adapted["skills"] = ["Python", "Kubernetes"]
        result = validate_adaptation(source, adapted)
        assert result.ok is False
        assert any("Kubernetes" in v for v in result.violations)
        assert "honesty" in result.reasoning.lower()

    def test_invented_company_rejected(self) -> None:
        """A company not present in source triggers a violation."""
        source = {
            "full_name": "Jane",
            "experience": [
                {
                    "title": "Engineer",
                    "company": "Acme",
                    "dates": "2020-2024",
                    "description": "Worked.",
                }
            ],
            "skills": [],
            "education": [],
            "languages": [],
        }
        adapted = {
            "full_name": "Jane",
            "experience": [
                {
                    "title": "Engineer",
                    "company": "Globex",
                    "dates": "2020-2024",
                    "description": "Worked.",
                }
            ],
            "skills": [],
            "education": [],
            "languages": [],
        }
        result = validate_adaptation(source, adapted)
        assert result.ok is False
        assert any("Globex" in v for v in result.violations)

    def test_invented_title_rejected(self) -> None:
        """A job title not present in source triggers a violation."""
        source = {
            "full_name": "Jane",
            "experience": [
                {
                    "title": "Backend Engineer",
                    "company": "Acme",
                    "dates": "2020-2024",
                    "description": "Worked.",
                }
            ],
            "skills": [],
            "education": [],
            "languages": [],
        }
        adapted = {
            "full_name": "Jane",
            "experience": [
                {
                    "title": "Staff Engineer",
                    "company": "Acme",
                    "dates": "2020-2024",
                    "description": "Worked.",
                }
            ],
            "skills": [],
            "education": [],
            "languages": [],
        }
        result = validate_adaptation(source, adapted)
        assert result.ok is False
        assert any("Staff Engineer" in v for v in result.violations)

    def test_fabricated_dates_rejected(self) -> None:
        """Dates that don't trace back to the source fail."""
        source = {
            "full_name": "Jane",
            "experience": [
                {
                    "title": "Engineer",
                    "company": "Acme",
                    "dates": "2020-2024",
                    "description": "Worked.",
                }
            ],
            "skills": [],
            "education": [],
            "languages": [],
        }
        adapted = {
            "full_name": "Jane",
            "experience": [
                {
                    "title": "Engineer",
                    "company": "Acme",
                    "dates": "2018-2025",
                    "description": "Worked.",
                }
            ],
            "skills": [],
            "education": [],
            "languages": [],
        }
        result = validate_adaptation(source, adapted)
        assert result.ok is False

    def test_description_with_new_tokens_rejected(self) -> None:
        """An adapted description that introduces new tokens fails."""
        source = {
            "full_name": "Jane",
            "experience": [
                {
                    "title": "Engineer",
                    "company": "Acme",
                    "dates": "2020-2024",
                    "description": "Built Python services on AWS.",
                }
            ],
            "skills": ["Python"],
            "education": [],
            "languages": [],
        }
        adapted = {
            "full_name": "Jane",
            "experience": [
                {
                    "title": "Engineer",
                    "company": "Acme",
                    "dates": "2020-2024",
                    "description": "Built quantum entanglement compilers for hyperscale cloud platforms.",
                }
            ],
            "skills": ["Python"],
            "education": [],
            "languages": [],
        }
        result = validate_adaptation(source, adapted)
        assert result.ok is False
        # Tokens like ``quantum``, ``entanglement``, ``compilers``,
        # ``hyperscale``, ``platforms`` are not in the source blob.
        assert len(result.violations) >= 1


# === Edge cases ===


class TestValidateAdaptationEdgeCases:
    """Empty inputs, missing keys, and partial CVs must not crash."""

    def test_empty_source_and_adapted(self) -> None:
        """Two empty dicts validate (no violations possible)."""
        result = validate_adaptation({}, {})
        assert result.ok is True

    def test_missing_experience_keys(self) -> None:
        """Adapted CV missing optional keys must not crash the validator."""
        source = {
            "full_name": "Jane",
            "experience": [],
            "skills": [],
            "education": [],
            "languages": [],
        }
        adapted = {"full_name": "Jane"}
        result = validate_adaptation(source, adapted)
        assert result.ok is True

    def test_empty_skill_strings_ignored(self) -> None:
        """Whitespace-only skills are normalized to empty and ignored."""
        source = {
            "full_name": "Jane",
            "experience": [],
            "skills": ["Python", "   ", ""],
            "education": [],
            "languages": [],
        }
        adapted = dict(source)
        adapted["skills"] = ["Python", "  ", ""]
        result = validate_adaptation(source, adapted)
        assert result.ok is True

    def test_diachronic_skills_normalized(self) -> None:
        """Adapted ``Python`` matches source ``Python`` even after diacritics."""
        source = {
            "full_name": "Jane",
            "experience": [],
            "skills": ["Pythón"],
            "education": [],
            "languages": [],
        }
        adapted = dict(source)
        adapted["skills"] = ["Python"]
        result = validate_adaptation(source, adapted)
        assert result.ok is True

    def test_returns_dataclass_instance(self) -> None:
        """The return type is always a ValidationResult dataclass."""
        result = validate_adaptation({"skills": ["Python"]}, {"skills": ["Python"]})
        assert isinstance(result, ValidationResult)
        assert isinstance(result.ok, bool)
        assert isinstance(result.violations, list)
        assert isinstance(result.reasoning, str)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Python", "python"),
        ("Node.js", "nodejs"),
        ("ReactJS", "reactjs"),
        ("Diseño", "diseno"),
        ("  Python  ", "python"),
    ],
)
def test_normalize_parametric(raw: str, expected: str) -> None:
    """Parametric sanity check matching the spec's normalize tests."""
    assert normalize(raw) == expected
