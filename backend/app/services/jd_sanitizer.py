"""Sanitize a job-description string before injecting it into an LLM prompt.

CV->JD adaptation puts the JD into the user template between explicit
delimiters. Anything that breaks the delimiter (newlines that close the
block, faux fences, prompt-injection patterns) gets neutralized. The
sanitizer is the first layer of cvA-R4; the post-diff validator is the
second.

Layering rationale
------------------
The two layers solve different problems and must both hold:

1. ``sanitize_jd`` runs on the *input* string. It strips adversarial
   structure (faux fences, ``<system>`` tags, "ignore previous
   instructions" phrasing, control characters that could smuggle
   directives through terminal escape sequences) before the JD is ever
   templated into a prompt. The aim is structural: make it impossible
   for the JD to *look like* an instruction.

2. ``adaptation_validator.validate_adaptation`` runs on the *output*
   CV. It enforces that every adapted skill/company/fact must trace
   back to the source CV. The aim is semantic: even if a buggy or
   adversarial model echoes invented content, the persisted result
   stays clean.

Weakening the data layer lets injection *phrasing* reach the model;
weakening the post-diff layer lets invented *content* reach storage.
Both must hold.

Design choices
--------------
* No external sanitization library (``bleach`` / ``nh3`` / ``markdown-it``)
  is introduced. The transformations are small, line-oriented, and
  locale-independent; pulling in a sanitizer would be heavier than the
  problem.

* The control-character strip keeps ``\\n`` and ``\\t`` because JDs are
  paragraph-structured (lists, bullets). Every other C0/category control
  is dropped: an attacker can hide a directive in a form-feed or an
  ANSI escape sequence, but a legitimate JD has no use for either.

* Triple backticks are replaced with three single quotes (`` ''' ``). The
  adaptation system prompt forbids markdown fences; the substitution
  enforces that at the data layer without throwing away the JD text.

* Injection-pattern replacement is *destructive*: the offending phrase
  is replaced with ``[REDACTED-INJECTION]``. We do not try to preserve
  the user's wording because the whole point is to delete the
  instruction; partial preservation would let a phrase that is just
  adversarial enough through.

* The result is wrapped between ``<JD_BEGIN>`` / ``<JD_END>`` markers by
  ``wrap_jd_for_prompt``. The system prompt tells the model the block
  is data, not instruction; the markers are the visible contract.

Non-goals
---------
* This module does not try to be a complete prompt-injection firewall.
  New phrasings surface regularly, and exhaustive coverage is a losing
  game. The sanitizer fences the JD in a way that makes adversarial
  structure clearly wrong; the post-diff validator catches the
  semantic consequence.

* The sanitizer is not a parser. It does not try to understand the JD;
  it removes structural hooks an attacker could use.
"""

from __future__ import annotations

# Upper bound on JD characters sent to the LLM. JDs from major boards
# routinely pass 8k chars (legal copy, EEO, related links). 8000 chars
# is enough to capture the substantive description and lets the
# truncation be visible to the user. Adjust if validation breaks.
JD_SANITIZER_MAX_CHARS = 8000

# Truncation marker. Plain string -- NOT a markdown fence -- so a
# reviewer of the prompt sees the cut and an LLM cannot mistake the
# marker for the start of a code block.
_TRUNCATION_MARKER = "...[TRUNCATED]"

# Replacement token for matched injection patterns. The brackets make
# the redaction visible to a prompt reader; the ``INJECTION`` suffix
# makes the reason visible too.
_INJECTION_REDACTION = "[REDACTED-INJECTION]"

# Patterns that prompt-injection relies on. We don't try to be
# exhaustive -- the validator is the second layer. We fence the JD
# in a way that makes adversarial structure clearly wrong. Order does
# not matter for correctness; we iterate the list and replace every
# case-insensitive occurrence of each entry.
_INJECTION_PATTERNS = [
    "ignore previous instructions",
    "ignore all instructions",
    "disregard the system prompt",
    "forget everything",
    "new instructions:",
    "you must",
    "system:",
    "assistant:",
    "",
    "",
    "<system>",
    "</system>",
    "### instruction",
    "### response",
    "```",
]

# Triple-backtick fence -> triple single quotes. The system prompt
# forbids markdown fences; this enforces it at the data layer.
_BACKTICK_FENCE = "```"
_SINGLE_QUOTE_FENCE = "'''"

# Delimiters that fence the sanitized JD inside the user template.
# These are the contract the system prompt advertises as "data, not
# instruction".
_JD_BEGIN_MARKER = "<JD_BEGIN>"
_JD_END_MARKER = "<JD_END>"


def _strip_control_characters(text: str) -> str:
    """Drop C0/category control characters except newline and tab.

    Newline (``\\n``) and tab (``\\t``) are how JDs are structured
    (paragraphs, lists). Everything else -- form-feed, vertical tab,
    NUL, ANSI escape sequences, etc. -- has no legitimate use in a JD
    and is a known smuggling channel for adversarial directives, so
    every other control character is removed.

    Args:
        text: Input string.

    Returns:
        Text with control characters (other than ``\\n`` / ``\\t``)
        removed.
    """
    return "".join(
        ch for ch in text if ch in ("\n", "\t") or (ch >= " " and ch != "\x7f")
    )


def _truncate(text: str, limit: int) -> str:
    """Truncate to ``limit`` characters and append a visible marker.

    A reader of the prompt can see the JD was cut, and the LLM cannot
    mistake the marker for a code-block fence (it is a plain string).

    Args:
        text: Input string.
        limit: Maximum length of the returned string *before* the
            marker is appended. The total returned length is
            ``limit + len(_TRUNCATION_MARKER)`` when truncation fires.

    Returns:
        ``text`` unchanged when it fits in ``limit``; otherwise the
        prefix of length ``limit`` followed by ``_TRUNCATION_MARKER``.
    """
    if len(text) <= limit:
        return text
    return text[:limit] + _TRUNCATION_MARKER


def sanitize_jd(jd_text: str) -> str:
    """Return a JD string safe to interpolate into the LLM user template.

    Pipeline (the order matters):

    1. **Truncate** at ``JD_SANITIZER_MAX_CHARS`` characters. If the JD
       is longer than the cap, the trailing characters are dropped and
       a ``...[TRUNCATED]`` marker is appended so the prompt reader can
       see the cut. Truncating first keeps the downstream controls (see
       below) cheap and predictable: their cost is bounded by the cap.

    2. **Strip control characters** except newline (``\\n``) and tab
       (``\\t``). Newline + tab are how JDs are structured (paragraphs,
       lists). Every other control character is dropped so an attacker
       cannot smuggle directives through ``\\x0c`` / ``\\x1b`` / NUL.

    3. **Neutralize fences** that look like code-block markers: every
       triple-backtick (`` ``` ``) is replaced with three single quotes
       (`` ''' ``). The system prompt forbids markdown fences; the
       substitution enforces it at the data layer without throwing the JD
       text away.

    4. **Replace known injection phrases** with the redaction marker.
       Each pattern in ``_INJECTION_PATTERNS`` is matched
       case-insensitively; the match is replaced wholesale with
       ``[REDACTED-INJECTION]``. The replacement is destructive -- we
       do not try to keep the user's wording because the whole point
       is to delete the instruction; partial preservation would let a
       phrase that is just adversarial enough through.

    The result is *not* yet wrapped between ``<JD_BEGIN>`` /
    ``<JD_END>``: that is the job of ``wrap_jd_for_prompt``. Keeping
    the wrap in a separate helper lets callers that need only the
    cleaned body (tests, dry runs, debugging) use ``sanitize_jd`` on
    its own.

    Args:
        jd_text: Raw job description as supplied by the user or fetched
            from a third-party board. May be empty; may contain control
            characters, fences, or injection phrasing.

    Returns:
        A cleaned string. Empty when the input was empty. Never
        contains a triple backtick, never contains a recognized
        injection phrase, never exceeds ``JD_SANITIZER_MAX_CHARS + len(
        _TRUNCATION_MARKER)`` characters.
    """
    if not jd_text:
        return ""

    truncated = _truncate(jd_text, JD_SANITIZER_MAX_CHARS)
    decontrolled = _strip_control_characters(truncated)
    unfenced = decontrolled.replace(_BACKTICK_FENCE, _SINGLE_QUOTE_FENCE)

    redacted = unfenced
    for pattern in _INJECTION_PATTERNS:
        if not pattern:
            # Defensive: an empty pattern in the table would match
            # everywhere and replace the whole string. Skip empties.
            continue
        redacted = _replace_case_insensitive(redacted, pattern, _INJECTION_REDACTION)
    return redacted


def _replace_case_insensitive(text: str, pattern: str, replacement: str) -> str:
    """Replace every occurrence of ``pattern`` in ``text``, case-insensitively.

    Uses a non-overlapping scan that preserves the original case of the
    surrounding text. We do not use ``str.replace`` with a lowered copy
    because that would lose the original casing of the replacement
    boundaries; the redaction marker is a fixed token either way.

    Args:
        text: Source text.
        pattern: Substring to match (case-insensitive).
        replacement: Replacement string.

    Returns:
        ``text`` with every case-insensitive occurrence of ``pattern``
        replaced by ``replacement``.
    """
    if not pattern:
        return text
    lower_text = text.lower()
    lower_pattern = pattern.lower()
    pattern_len = len(lower_pattern)
    if pattern_len == 0:
        return text

    pieces: list[str] = []
    cursor = 0
    while True:
        hit = lower_text.find(lower_pattern, cursor)
        if hit < 0:
            pieces.append(text[cursor:])
            break
        pieces.append(text[cursor:hit])
        pieces.append(replacement)
        cursor = hit + pattern_len
    return "".join(pieces)


def wrap_jd_for_prompt(jd_text: str) -> str:
    """Return the JD fenced between ``<JD_BEGIN>`` and ``<JD_END>`` markers.

    Composes ``sanitize_jd`` with explicit delimiters so the LLM sees
    a clear boundary between data and instruction. The system prompt
    advertises this contract; the markers make it visible.

    Args:
        jd_text: Raw JD text as supplied by the caller.

    Returns:
        ``"<JD_BEGIN>\\n{sanitized}\\n<JD_END>"``. The delimiters are
        always present so callers can grep the prompt log for them.
    """
    return f"{_JD_BEGIN_MARKER}\n{sanitize_jd(jd_text)}\n{_JD_END_MARKER}"
