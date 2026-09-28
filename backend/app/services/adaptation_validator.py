"""
Adaptation honesty validator (Slice A, sprint-adapt-cv-outreach, PR2).

The validator is the no-honesty-violation gate between the LLM and the
persisted adapted CV. It enforces that the LLM did not invent skills,
companies, or facts not present in the source CV.

Pipeline
--------
1. ``normalize`` lowercase, strip diacritics (NFKD + drop combining
   marks), strip non-alphanumeric except whitespace, collapse runs of
   whitespace, and strip common suffixes (``s`` / ``es`` / ``.`` / ``·``).
2. ``_build_source_index`` flattens source skills, companies, and
   experience metadata into normalized-token sets + a single normalized
   blob of the experience bullet text.
3. ``validate_adaptation`` checks every adapted skill/company is a
   substring of the corresponding normalized source set; experience
   metadata (title/company/dates) is checked as substrings; rewritten
   descriptions are tokenized and every token longer than 2 chars must
   appear in the source description blob.

Why substring match after normalization
---------------------------------------
We don't use embeddings or strict equality because legitimate rewrites
add stopwords and synonyms (``ReactJS`` vs ``React``, ``Node.js`` vs
``Node``). Normalization collapses these; substring match then accepts
``reactjs`` inside a source blob containing ``react``. We are NOT
trying to verify semantic truth — the model is told in the system
prompt not to invent, and we verify by lexical provenance.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

# Minimum token length to bother checking against the source blob. Short
# tokens (≤2 chars) are stopwords/numerals and almost always missing even
# from verbatim copies after normalization strips punctuation.
_MIN_TOKEN_LEN = 3

# Non-alphanumeric chars we drop (anything outside [a-z0-9 ] after
# NFKD normalization). This handles ``.`` (Node.js → nodejs), ``-``
# (cross-platform → crossplatform), ``/`` (CI/CD → cicd), ``·`` (middle
# dots), etc. in a single pass.
_NON_ALNUM_RE = re.compile(r"[^a-z0-9\s]+")

# Whitespace runs collapse to a single space.
_WS_RE = re.compile(r"\s+")


@dataclass
class ValidationResult:
    """Outcome of validating an LLM-emitted adapted CV against a source CV.

    Attributes:
        ok: ``True`` when no violations were detected.
        violations: Human-readable descriptions of each leaked/invented
            token. Empty when ``ok`` is True.
        reasoning: Short summary useful for logs / error responses.
    """

    ok: bool
    violations: list[str] = field(default_factory=list)
    reasoning: str = ""


def normalize(s: str) -> str:
    """Normalize a token or short text for honest substring comparison.

    Steps:
        1. ``unicodedata.normalize("NFKD", s)`` to split diacritics from
           base characters (``é`` → ``e`` + combining acute).
        2. Drop combining marks.
        3. Lowercase.
        4. Strip non-alphanumeric chars except spaces (kills ``.``, ``-``,
           ``/``, ``·``, etc.).
        5. Collapse runs of whitespace.

    We deliberately do NOT strip trailing ``s``/``es`` for plurals:
    ``ReactJS`` → ``reactjs`` is the desired form (the ``s`` is part of
    the ``JS`` abbreviation, not a plural). Plural matching is handled
    by the bidirectional substring check in ``_is_substring_of`` —
    ``python`` (source) matches adapted ``pythons`` because we test
    ``needle in hay`` in either direction.

    Args:
        s: Input string (skill name, company, description, etc.).

    Returns:
        Normalized form suitable for substring matching.

    Examples:
        >>> normalize("ReactJS")
        'reactjs'
        >>> normalize("Node.js")
        'nodejs'
        >>> normalize("Diseño")
        'diseno'
        >>> normalize("  Python  ")
        'python'
    """
    if not s:
        return ""
    decomposed = unicodedata.normalize("NFKD", s)
    # Drop combining marks (accents etc.)
    ascii_form = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    lowered = ascii_form.lower()
    # Replace anything not a-z/0-9 with empty. This collapses
    # ``.``, ``-``, ``/``, ``·``, etc. so ``Node.js`` → ``nodejs`` and
    # ``cross-platform`` → ``crossplatform`` in a single pass — we
    # explicitly use ``""`` (not ``" "``) so we don't introduce
    # separator whitespace that would block substring matching of
    # concatenated tokens.
    cleaned = _NON_ALNUM_RE.sub("", lowered)
    # Collapse any whitespace that pre-existed in the source.
    cleaned = _WS_RE.sub(" ", cleaned).strip()
    return cleaned


def _source_blob(experience: list[dict]) -> str:
    """Build a single normalized blob of every experience bullet.

    Args:
        experience: List of experience dicts with a ``description`` key.

    Returns:
        Concatenated normalized descriptions (whitespace-separated).
    """
    parts: list[str] = []
    for exp in experience or []:
        desc = exp.get("description") or ""
        if desc:
            parts.append(normalize(desc))
    return " ".join(parts)


def _source_set(items: list[str]) -> set[str]:
    """Normalize a list of strings into a deduped set."""
    return {normalize(item) for item in items if item}


def _is_substring_of(needle: str, haystack: set[str]) -> bool:
    """Return True when ``needle`` matches any element of ``haystack``.

    A match happens when the needle equals an element OR appears as a
    substring of an element. Empty needles never match.
    """
    if not needle:
        return False
    for hay in haystack:
        if not hay:
            continue
        if needle in hay or hay in needle:
            return True
    return False


def _validate_descriptions(
    source_blob: str,
    adapted_experience: list[dict],
) -> list[str]:
    """Token-level check on rewritten experience descriptions.

    Splits each adapted description into normalized tokens (length ≥
    ``_MIN_TOKEN_LEN``) and verifies each token appears in the source
    blob. Stopword-level words are dropped by the length filter.

    Args:
        source_blob: Pre-normalized concatenation of source descriptions.
        adapted_experience: Adapted experience blocks.

    Returns:
        List of violation strings (empty when clean).
    """
    if not source_blob:
        return []
    violations: list[str] = []
    for idx, exp in enumerate(adapted_experience or []):
        desc = exp.get("description") or ""
        if not desc:
            continue
        norm_desc = normalize(desc)
        tokens = norm_desc.split()
        for token in tokens:
            if len(token) < _MIN_TOKEN_LEN:
                continue
            if token in source_blob:
                continue
            violations.append(
                f"experience[{idx}].description leaks token '{token}'"
            )
    return violations


def validate_adaptation(source: dict, adapted: dict) -> ValidationResult:
    """Validate an LLM-emitted adapted CV against the source CV.

    Enforces the Slice A honesty contract: every adapted skill and
    company must be a substring of the source after normalization; every
    experience block's metadata (title/company/dates) must likewise
    originate from the source; rewritten descriptions may only contain
    tokens that already exist in the source description blob.

    The model is given permission to REWRITE bullets but not to INVENT
    facts; this is the gate that prevents silent drift.

    Args:
        source: Source CV in the same shape as ``UserCV.structured``
            (``full_name``, ``experience``, ``skills``, ``education``,
            ``languages``).
        adapted: Adapted CV in the same shape as ``source``.

    Returns:
        ``ValidationResult(ok=True, ...)`` when the adapted CV is honest.
        ``ValidationResult(ok=False, violations=[...], reasoning="...")``
        otherwise.
    """
    violations: list[str] = []

    source_skills = _source_set(source.get("skills", []))
    source_companies: set[str] = set()
    source_titles: set[str] = set()
    source_dates: set[str] = set()
    for exp in source.get("experience", []) or []:
        if exp.get("company"):
            source_companies.add(normalize(exp["company"]))
        if exp.get("title"):
            source_titles.add(normalize(exp["title"]))
        if exp.get("dates"):
            source_dates.add(normalize(exp["dates"]))
    source_blob = _source_blob(source.get("experience", []))

    # Skills: every adapted skill must trace back to a source skill.
    for skill in adapted.get("skills", []) or []:
        norm_skill = normalize(skill)
        if not norm_skill:
            continue
        if not _is_substring_of(norm_skill, source_skills):
            violations.append(f"skill '{skill}' not present in source")

    # Companies: every adapted company must trace back to a source company.
    for exp in adapted.get("experience", []) or []:
        company = exp.get("company") or ""
        norm_company = normalize(company)
        if not norm_company:
            continue
        if not _is_substring_of(norm_company, source_companies):
            violations.append(f"company '{company}' not present in source")

    # Experience metadata (title, dates) must also trace back. Companies
    # are checked above; titles and dates round out the verbatim fields.
    for exp in adapted.get("experience", []) or []:
        title = exp.get("title") or ""
        norm_title = normalize(title)
        if norm_title and not _is_substring_of(norm_title, source_titles):
            violations.append(f"title '{title}' not present in source")
        dates = exp.get("dates") or ""
        norm_dates = normalize(dates)
        if norm_dates and not _is_substring_of(norm_dates, source_dates):
            violations.append(f"dates '{dates}' not present in source")

    # Description: token-level provenance check on the rewritten bullets.
    violations.extend(
        _validate_descriptions(source_blob, adapted.get("experience", []) or [])
    )

    if violations:
        return ValidationResult(
            ok=False,
            violations=violations,
            reasoning=f"adapted CV contains {len(violations)} honesty violation(s)",
        )

    return ValidationResult(
        ok=True,
        violations=[],
        reasoning="adapted CV is a documented rewrite of the source",
    )
