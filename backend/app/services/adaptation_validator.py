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
4. Numbers in those descriptions are checked by a separate rule (see
   ``NumericClaim``) because a length filter cannot judge them: a
   fabricated metric is usually short ("40%", "2M"), and a legitimate
   rewrite reformats it into something that is no longer a literal
   substring of the source.

Why substring match after normalization
---------------------------------------
We don't use embeddings or strict equality because legitimate rewrites
add stopwords and synonyms (``ReactJS`` vs ``React``, ``Node.js`` vs
``Node``). Normalization collapses these; substring match then accepts
``reactjs`` inside a source blob containing ``react``. We are NOT
trying to verify semantic truth — the model is told in the system
prompt not to invent, and we verify by lexical provenance.

What this validator does NOT catch
----------------------------------
Lexical provenance is not claim provenance. The source blob mixes every
experience block, so a phrase (or a number) belonging to job 3 can be
moved into job 1 with no violation; a number that genuinely appears in
the source can be re-attached to a different achievement of the same
unit; and ``full_name``, ``education`` and ``languages`` are not
inspected at all. Numeric claims are verified as *values with a unit*,
never as *"this number attached to this achievement"*.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

# Minimum token length to bother checking against the source blob. This
# filter applies to WORDS only. Short *numbers* are not stopwords — they
# are the highest-value fabrication target there is ("revenue by 40%") —
# so they are excluded from this filter and governed by the numeric rule
# in ``_extract_numeric_claims``.
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


# ---------------------------------------------------------------------------
# Numeric claims
# ---------------------------------------------------------------------------
# A fabricated achievement almost always carries a magnitude ("increased
# revenue by 40%", "served 2M events/day", "grew the team 5x"). Those are
# exactly the tokens the length filter drops, so the filter cannot be
# repaired by lowering it: a legitimate rewrite *reformats* numbers
# ("300k" → "300,000", "2M" → "two million", "40%" → "forty percent"), and
# the reformatted value is no longer a literal substring of the source.
#
# So numbers get their own rule. Every number in an adapted bullet is
# extracted as a ``NumericClaim`` — a canonical (value, unit) pair — and
# must be reconstructible from a claim extracted the same way from the
# source bullets. Extraction is symmetric (same function, both sides), so
# all of the normalizations above are handled once instead of per format.

# Units. ``plain`` covers bare numbers and magnitude-suffixed numbers:
# a magnitude is a *formatting* choice ("2M" and "2000000" are the same
# claim), not a semantic unit, so it never has to match a source unit.
# Percent and multiplier DO carry meaning — "3x" and "300%" are different
# claims about the same value — so they must match the source's unit.
_UNIT_PLAIN = "plain"
_UNIT_PERCENT = "percent"
_UNIT_MULTIPLIER = "multiplier"

# Multiplicative suffixes attached to a digit run. Checked by lookahead
# (not baked into the regex) so that "120ms" yields a plain 120 while
# "2M" yields 2000000 and "5x" yields a multiplier.
_SUFFIX_VALUES: dict[str, Decimal] = {
    "k": Decimal(1000),
    "m": Decimal(10**6),
    "mm": Decimal(10**6),
    "b": Decimal(10**9),
    "bn": Decimal(10**9),
}

# A digit run. The negative lookbehind keeps digits glued to an identifier
# ("sha256", "utf8", "p99") out of the claim set: those are labels, not
# claims, and treating them as claims only creates false rejections.
_DIGIT_RUN_RE = re.compile(r"(?<![a-z0-9])\d(?:[\d.,]*\d)?")

# Word tokens, classified against the tables below.
_WORD_RE = re.compile(r"[a-z]+")

# Number words, English and Spanish. The source CVs and the rewritten
# bullets are written in both, and a half-translated table would reject
# truthful rewrites.
_NUMBER_WORDS: dict[str, Decimal] = {
    "zero": Decimal(0),
    "one": Decimal(1),
    "two": Decimal(2),
    "three": Decimal(3),
    "four": Decimal(4),
    "five": Decimal(5),
    "six": Decimal(6),
    "seven": Decimal(7),
    "eight": Decimal(8),
    "nine": Decimal(9),
    "ten": Decimal(10),
    "eleven": Decimal(11),
    "twelve": Decimal(12),
    "thirteen": Decimal(13),
    "fourteen": Decimal(14),
    "fifteen": Decimal(15),
    "sixteen": Decimal(16),
    "seventeen": Decimal(17),
    "eighteen": Decimal(18),
    "nineteen": Decimal(19),
    "twenty": Decimal(20),
    "thirty": Decimal(30),
    "forty": Decimal(40),
    "fifty": Decimal(50),
    "sixty": Decimal(60),
    "seventy": Decimal(70),
    "eighty": Decimal(80),
    "ninety": Decimal(90),
    "cero": Decimal(0),
    "dos": Decimal(2),
    "tres": Decimal(3),
    "cuatro": Decimal(4),
    "cinco": Decimal(5),
    "seis": Decimal(6),
    "siete": Decimal(7),
    "ocho": Decimal(8),
    "nueve": Decimal(9),
    "diez": Decimal(10),
    "once": Decimal(11),
    "doce": Decimal(12),
    "trece": Decimal(13),
    "catorce": Decimal(14),
    "quince": Decimal(15),
    "dieciseis": Decimal(16),
    "diecisiete": Decimal(17),
    "dieciocho": Decimal(18),
    "diecinueve": Decimal(19),
    "veinte": Decimal(20),
    "treinta": Decimal(30),
    "cuarenta": Decimal(40),
    "cincuenta": Decimal(100),
    "sesenta": Decimal(60),
    "setenta": Decimal(70),
    "ochenta": Decimal(80),
    "noventa": Decimal(90),
    # The 500-900 hundreds are single words in Spanish, and a Spanish CV
    # writes "quinientos clientes" far more often than "500 clientes".
    "doscientos": Decimal(200),
    "trescientos": Decimal(300),
    "cuatrocientos": Decimal(400),
    "quinientos": Decimal(500),
    "seiscientos": Decimal(600),
    "setecientos": Decimal(700),
    "ochocientos": Decimal(800),
    "novecientos": Decimal(900),
}

# Words that scale the numeral they follow ("five hundred" → 500). Plurals
# are resolved by the lookup in ``_classify_word``.
_MAGNITUDE_WORDS: dict[str, Decimal] = {
    "hundred": Decimal(100),
    "thousand": Decimal(1000),
    "million": Decimal(10**6),
    "billion": Decimal(10**9),
    "trillion": Decimal(10**12),
    "cien": Decimal(100),
    "ciento": Decimal(100),
    "mil": Decimal(1000),
    "millon": Decimal(10**6),
    "billon": Decimal(10**12),
}

# Units expressed as words.
_PERCENT_WORDS = frozenset({"percent", "porciento", "porcentaje", "pct"})
_MULTIPLIER_WORDS = frozenset({"times", "veces", "fold"})

# Joiners that are transparent *inside* a number phrase ("one hundred and
# fifty" → 150) and inert outside it. The Spanish articles are here on
# purpose: "un" is the number 1 in "un millón" but a bare article in
# "un equipo de 5", and counting it as a claim of 1 would reject truthful
# rewrites that swap an article. "por" is here because "por ciento" is one
# percent marker and its first word is not a claim of its own.
_TRANSPARENT_WORDS = frozenset(
    {"and", "y", "e", "a", "an", "un", "una", "uno", "por"}
)

# "por ciento" is a two-word percent marker; merging it up front stops
# "ciento" from being read as the number 100.
_POR_CENTO_HEAD = "por"
_POR_CENTO_TAILS = frozenset({"ciento", "cien"})

# Symbols folded to a single ASCII counterpart before extraction, so the
# multiplier sign ("5×") behaves like "5x". Every entry must be exactly
# one character wide to keep span offsets aligned with the input.
_SYMBOL_FOLD = {"×": "x", "✕": "x", "％": "%"}


@dataclass(frozen=True)
class NumericClaim:
    """A number extracted from CV text, reduced to what it actually claims.

    Attributes:
        value: The canonical magnitude. Suffixes and magnitude words are
            expanded ("2M" and "two million" both become ``2000000``) and
            thousands separators are removed, so two spellings of the same
            number compare equal.
        unit: ``plain``, ``percent`` or ``multiplier``. A magnitude is
            reported as ``plain`` because "2M" and "2000000" make the same
            claim; a percentage or a multiplier is not interchangeable
            with a bare number, so it keeps its identity.
        surface: The text the claim was read from ("40%", "two million"),
            so a violation message points at something the model can act on.
    """

    value: Decimal
    unit: str
    surface: str


@dataclass(frozen=True)
class _NumItem:
    """One classified piece of text on the way to becoming a claim."""

    tag: str  # "num" | "magnitude" | "percent" | "multiplier" | "other" | "transparent"
    value: Decimal
    start: int
    end: int
    unit: str = _UNIT_PLAIN
    word: str = ""
    standalone: bool = False
    break_before: bool = False


def _clean_with_offsets(text: str) -> tuple[str, list[int]]:
    """Lowercase and strip diacritics, keeping a map back to the input.

    Diacritic stripping changes the length of the string ("millón" is 6
    characters, "millon" is 7 with the combining acute dropped), so the
    caller needs ``origin[i]`` to translate a span in the cleaned text
    back into a span of the original for the violation message.

    Returns:
        The cleaned text and, for each of its characters, the index of the
        source character it came from.
    """
    chars: list[str] = []
    origin: list[int] = []
    for index, char in enumerate(text):
        for piece in unicodedata.normalize("NFKD", _SYMBOL_FOLD.get(char, char)):
            if unicodedata.combining(piece):
                continue
            chars.append(piece.lower())
            origin.append(index)
    return "".join(chars), origin


def _parse_digit_run(text: str) -> Decimal | None:
    """Read a digit run, deciding between grouping and decimal separators.

    ``300,000`` and ``1.200`` are one number; ``1.5`` and ``1,5`` are a
    decimal. The discriminator is the width of the trailing group: exactly
    three digits means grouping, anything shorter means a decimal point.
    The same text is read the same way on both sides of the comparison, so
    the ambiguous ``1.500`` is consistent even though it is a guess.

    Args:
        text: A run of digits possibly containing ``.`` or ``,``.

    Returns:
        The value, or ``None`` when the run is not a number at all.
    """
    parts = re.split(r"[.,]", text)
    try:
        if len(parts) == 1:
            return Decimal(parts[0])
        if all(len(part) == 3 for part in parts[1:]) and 1 <= len(parts[0]) <= 3:
            return Decimal("".join(parts))
        return Decimal(f"{parts[0]}.{''.join(parts[1:])}")
    except InvalidOperation:
        return None


def _classify_word(word: str) -> tuple[str, Decimal]:
    """Map a word to ``(tag, value)``; unknown words are inert.

    Spanish plurals ("miles", "millones", "billardos") are resolved by
    retrying with the ``es``/``s`` ending removed.
    """
    for candidate in (word, word[:-2] if word.endswith("es") else word, word[:-1]):
        if candidate in _NUMBER_WORDS:
            return "num", _NUMBER_WORDS[candidate]
        if candidate in _MAGNITUDE_WORDS:
            return "magnitude", _MAGNITUDE_WORDS[candidate]
    if word in _PERCENT_WORDS:
        return "percent", Decimal(0)
    if word in _MULTIPLIER_WORDS:
        return "multiplier", Decimal(0)
    if word in _SUFFIX_VALUES:
        return "magnitude", _SUFFIX_VALUES[word]
    if word == "x":
        return "multiplier", Decimal(0)
    if word in _TRANSPARENT_WORDS:
        return "transparent", Decimal(0)
    return "other", Decimal(0)


def _extract_numeric_claims(text: str) -> list[NumericClaim]:
    """Extract every numeric claim from a piece of CV text.

    Recognizes digit runs (with grouping/decimal separators and magnitude
    or multiplier suffixes), percent markers (``%``, ``percent``, ``por
    ciento``), and spelled-out numbers in English and Spanish, including
    composition ("two hundred fifty" → 250, "two million five hundred
    thousand" → 2500000).

    Digits glued to an identifier ("sha256", "utf8", "p99") are treated as
    labels and produce no claim: they are not numbers the candidate is
    claiming credit for, and inventing a claim from them would reject
    truthful rewrites.

    Args:
        text: Raw (un-normalized) CV text. Raw matters — ``normalize``
            deletes the decimal point, which would turn "1.2M" into
            twelve million.

    Returns:
        Claims in document order. Each number produces exactly one claim.
    """
    cleaned, origin = _clean_with_offsets(text)
    if not cleaned:
        return []

    items: list[_NumItem] = []
    covered: list[tuple[int, int]] = []

    # Pass 1 — digit runs, with a lookahead for an attached unit. A run
    # separated from the previous one by a single space and carrying
    # exactly three digits continues it: "300 000" is one number. Any
    # other separator ends the number, so "50-200" and "2020-2024" stay
    # two claims each instead of being summed into 250 and 4044.
    runs = [match.span() + (match.group(0),) for match in _DIGIT_RUN_RE.finditer(cleaned)]
    index = 0
    while index < len(runs):
        start, end, chunk = runs[index]
        pieces = [chunk]
        while index + 1 < len(runs):
            next_start, next_end, next_chunk = runs[index + 1]
            gap = cleaned[end:next_start]
            if gap.strip() or len(gap) > 1 or len(next_chunk) != 3:
                break
            pieces.append(next_chunk)
            end = next_end
            index += 1
        index += 1
        value = _parse_digit_run("".join(pieces))
        if value is None:
            continue
        unit = _UNIT_PLAIN
        probe = end + 1 if cleaned[end : end + 2] == " %" else end
        if cleaned[probe : probe + 1] == "%":
            unit = _UNIT_PERCENT
            end = probe + 1
        for size in (2, 1):
            if unit != _UNIT_PLAIN:
                break
            tail = cleaned[end : end + size]
            after = cleaned[end + size : end + size + 1]
            if len(tail) < size or not tail.isalpha() or after.isalpha():
                continue
            if tail in _SUFFIX_VALUES:
                value *= _SUFFIX_VALUES[tail]
                end += size
                break
            if tail == "x":
                unit = _UNIT_MULTIPLIER
                end += size
                break
        covered.append((start, end))
        # A number that carries its own unit is a complete claim and is
        # never merged into a neighbouring phrase ("2m and 300k" is two
        # claims, not 2000300).
        items.append(
            _NumItem(
                tag="num",
                value=value,
                start=start,
                end=end,
                unit=unit,
                standalone=unit != _UNIT_PLAIN,
                # A run that does not start right after whitespace is not
                # a continuation of the phrase before it, so it opens its
                # own claim: "50-200" and "1/2" are two numbers, not 250
                # and 3.
                break_before=start == 0 or not cleaned[start - 1].isspace(),
            )
        )

    # Pass 2 — words, skipping any span the digit pass already consumed
    # (the "m" of "2M", the "x" of "5x").
    for match in _WORD_RE.finditer(cleaned):
        start, end = match.span()
        if any(start >= lo and end <= hi for lo, hi in covered):
            continue
        word = match.group(0)
        tag, value = _classify_word(word)
        items.append(_NumItem(tag=tag, value=value, start=start, end=end, word=word))

    items.sort(key=lambda item: item.start)

    # Merge the two-word percent marker "por ciento" so its "ciento" is
    # not read as the number 100.
    merged: list[_NumItem] = []
    index = 0
    while index < len(items):
        current = items[index]
        following = items[index + 1] if index + 1 < len(items) else None
        if (
            current.word == _POR_CENTO_HEAD
            and following is not None
            and following.tag == "magnitude"
            and following.word in _POR_CENTO_TAILS
        ):
            merged.append(
                _NumItem(
                    tag="percent",
                    value=Decimal(0),
                    start=current.start,
                    end=following.end,
                    word="por ciento",
                )
            )
            index += 2
            continue
        merged.append(current)
        index += 1
    items = merged

    claims: list[NumericClaim] = []
    # ``total`` holds completed groups ("two million ..."), ``group`` the
    # one being assembled ("... five hundred"). "hundred" scales the group
    # in place; "thousand" and above close the group into the total, which
    # is what makes "two million five hundred thousand" → 2500000 while
    # "five hundred thousand" → 500000.
    total = Decimal(0)
    group = Decimal(0)
    is_open = False
    run_start = 0
    run_end = 0

    def flush(unit: str, end: int) -> None:
        nonlocal total, group, is_open
        if not is_open:
            return
        surface = text[origin[run_start] : origin[end - 1] + 1] if end > run_start else ""
        claims.append(
            NumericClaim(
                value=total + group,
                unit=unit,
                surface=_WS_RE.sub(" ", surface).strip(),
            )
        )
        total = Decimal(0)
        group = Decimal(0)
        is_open = False

    index = 0
    while index < len(items):
        item = items[index]
        if item.tag in ("other", "transparent"):
            following = items[index + 1] if index + 1 < len(items) else None
            if (
                item.tag == "transparent"
                and is_open
                and following is not None
                and following.tag in ("num", "magnitude")
            ):
                # "one hundred and fifty" — keep the joiner in the surface
                # text but out of the arithmetic.
                run_end = item.end
                index += 1
                continue
            flush(_UNIT_PLAIN, run_end)
            index += 1
            continue
        if item.tag in ("percent", "multiplier"):
            flush(item.tag, item.end)
            index += 1
            continue
        if item.tag == "num":
            if item.break_before:
                flush(_UNIT_PLAIN, run_end)
            if not is_open:
                is_open = True
                run_start = item.start
            run_end = item.end
            group += item.value
            if item.standalone:
                flush(item.unit, item.end)
            index += 1
            continue
        # "magnitude" — scales the group, or closes it when >= 1000.
        if not is_open:
            is_open = True
            run_start = item.start
        run_end = item.end
        scale = group if group else Decimal(1)
        if item.value >= 1000:
            total += scale * item.value
            group = Decimal(0)
        else:
            group = scale * item.value
        index += 1

    flush(_UNIT_PLAIN, run_end)
    return claims


def _same_value(left: Decimal, right: Decimal) -> bool:
    """Whether two canonical values describe the same quantity.

    Truncation to a whole number is tolerated, because a rewrite that
    rounds "Python 3.11" down to "Python 3" is not inventing anything and
    must not cost the candidate their adaptation. The leniency stops at
    the first decimal place: "3.11" and "3.9" are different runtimes, and
    rounding one to the other is exactly the substitution this rule exists
    to catch. Two values with fractional parts must be equal.

    Returns:
        True when the values may be treated as the same number.
    """
    if left == right:
        return True
    if left != left.to_integral_value() and right != right.to_integral_value():
        return False
    return int(left) == int(right)


def _units_compatible(adapted_unit: str, source_unit: str) -> bool:
    """Whether a source claim can back an adapted claim of ``adapted_unit``.

    Dropping a unit is a reformat ("18 percent" → "18"), so a bare number
    is satisfied by any source claim of the same value. Adding one is not:
    re-labelling a real "18 engineers" as "increased revenue by 18%" is a
    new claim, not a rewrite.
    """
    if adapted_unit == _UNIT_PLAIN:
        return True
    return adapted_unit == source_unit


def _is_backed_by_source(claim: NumericClaim, source_claims: list[NumericClaim]) -> bool:
    """Whether the source CV really claims this value, with this unit."""
    return any(
        _same_value(claim.value, candidate.value)
        and _units_compatible(claim.unit, candidate.unit)
        for candidate in source_claims
    )


def _is_numeric_domain(token: str) -> bool:
    """Whether a normalized token is governed by the numeric rule.

    These tokens are exempt from the word/substring check, because their
    spelling is exactly what a legitimate rewrite changes ("300k" →
    "300000", "2M" → "million", "forty"). Every token matched here is read
    by ``_extract_numeric_claims`` on the raw text, so no claim escapes
    verification by being exempted — with one harmless exception: a bare
    "x", which carries no number and is already under the length filter.
    """
    if not token:
        return False
    if token.isdigit():
        return True
    head = len(token) - len(token.lstrip("0123456789"))
    if head and len(token) - head <= 2:
        # "2m", "5x", "120ms" — a digit run with at most two letters.
        return True
    if token in _NUMBER_WORDS or token in _MAGNITUDE_WORDS:
        return True
    return _classify_word(token)[0] in (
        "num",
        "magnitude",
        "percent",
        "multiplier",
        "transparent",
    )


def _raw_description_text(experience: list[dict]) -> str:
    """Concatenate the *un-normalized* experience bullets.

    The numeric rule needs the original text: ``normalize`` deletes the
    decimal point, so "1.2M" would arrive as ``12m`` (twelve million) and
    the percent sign would be gone entirely.

    Args:
        experience: List of experience dicts with a ``description`` key.

    Returns:
        The raw descriptions joined by a single space.
    """
    parts = [exp.get("description") or "" for exp in experience or []]
    return " ".join(part for part in parts if part)


def _validate_descriptions(
    source_blob: str,
    source_claims: list[NumericClaim],
    adapted_experience: list[dict],
) -> list[str]:
    """Token-level check on rewritten experience descriptions.

    Two rules run over every bullet, and they partition the tokens:

    1. **Numeric rule.** Every ``NumericClaim`` in the bullet must be
       reconstructible from the claims extracted from the source bullets
       (same canonical value, compatible unit). This is the rule that
       governs numbers regardless of their length, so "40%", "2M" and
       "5x" are checked while "300,000", "two million" and "forty" —
       reformats of numbers the source really did claim — are not
       rejected merely for not being literal substrings.
    2. **Token rule.** Every other token longer than 2 chars must appear
       in the normalized source blob. Unchanged.

    Args:
        source_blob: Pre-normalized concatenation of source descriptions.
        source_claims: Numeric claims extracted from the raw source
            descriptions, used by the numeric rule.
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
        for claim in _extract_numeric_claims(desc):
            if _is_backed_by_source(claim, source_claims):
                continue
            violations.append(
                f"experience[{idx}].description contains unverified metric '{claim.surface}'"
            )
        norm_desc = normalize(desc)
        tokens = norm_desc.split()
        for token in tokens:
            if _is_numeric_domain(token):
                continue
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
    tokens that already exist in the source description blob, and every
    number in them must be a value the source bullets actually claim.

    The model is given permission to REWRITE bullets but not to INVENT
    facts; this is the gate that prevents silent drift.

    The numeric rule, in one sentence: a number in an adapted bullet is
    accepted only if the source bullets contain the same canonical value
    (separators, currency symbols, magnitude suffixes, magnitude words and
    spelled-out numbers all canonicalize to the same number) and the
    source does not contradict its unit — a bare number may be sourced
    from a percentage or a multiplier (dropping the unit is a reformat),
    but a percentage or a multiplier must be sourced from the same unit.

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
    source_claims = _extract_numeric_claims(
        _raw_description_text(source.get("experience", []))
    )

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

    # Description: token-level provenance plus numeric-claim provenance on
    # the rewritten bullets.
    violations.extend(
        _validate_descriptions(
            source_blob,
            source_claims,
            adapted.get("experience", []) or [],
        )
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
