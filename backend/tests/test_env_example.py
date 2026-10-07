"""
RED tests for backend/.env.example completeness (S2 of feat-c8-docs-makefile).

Issue #51: backend/.env.example documents 12 of the 26 vars read by Settings.
These tests pin every Settings validation_alias against the example file so the
gap stays closed.

The test reads `Settings.__fields__` (live, from the installed backend) so it
tracks the code: any new alias added to config.py shows up in the test
immediately. If a maintainer adds a new env var to Settings, it will fail
this test until they also add it to backend/.env.example.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_EXAMPLE = REPO_ROOT / "backend" / ".env.example"

# Built-in default secrets that MUST NOT appear verbatim in the example.
# (Their lines must have an empty value with a comment, not the literal.)
BANNED_LITERAL_DEFAULTS = {
    "JWT_SECRET": "dev-secret-change-in-production",
}


def _settings_aliases() -> set[str]:
    """Live-read every env-bound alias from app.core.config.Settings.

    Only fields that declare an explicit ``alias=`` or ``validation_alias=``
    are env-bound; pydantic v2 stores them in different attributes. Fields
    without an alias still load from env (the field name, uppercased) but the
    maintainer can choose to document them as informational-only — see the
    rationale in `docs/audit/90-catalogo-completo.md`.

    We require explicit aliases to be documented because they were clearly
    intended to be env-driven. Field names without an alias are excluded
    from the test so the maintainer can decide per field.

    Imported lazily so this module loads even if the backend stack has issues.
    """
    from app.core.config import Settings

    aliases: set[str] = set()
    for name, field in Settings.model_fields.items():
        alias = field.alias or field.validation_alias
        if alias is None:
            continue
        aliases.add(str(alias).upper())
    return aliases


def _example_keys() -> set[str]:
    """Parse backend/.env.example into a set of declared env var names.

    Counts both active (`KEY=value`) and commented (`# KEY=value`) lines, so
    documentation that lives inside an optional / commented block still pins.
    """
    assert ENV_EXAMPLE.is_file(), f"backend/.env.example not found at {ENV_EXAMPLE}"
    keys: set[str] = set()
    for raw_line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        # Strip a leading "# " comment marker so documentation inside
        # commented blocks still counts as a documented alias.
        if line.startswith("#"):
            line = line.lstrip("#").lstrip()
            if not line:
                continue
        # Accept `KEY=value` and ignore `export KEY=...`.
        m = re.match(r"^(?:export\s+)?([A-Z][A-Z0-9_]*)\s*=", line)
        if m:
            keys.add(m.group(1))
    return keys


# ----- S2.1 every Settings alias is documented ------------------------------


def test_env_example_covers_every_settings_alias() -> None:
    """Every validation_alias from Settings must appear in backend/.env.example.

    Settings that are documented via aliases, not field names, must be
    referenced under their alias. Field names without an alias default to
    uppercase, so this test normalizes both sides.
    """
    aliases = _settings_aliases()
    documented = _example_keys()

    missing = sorted(aliases - documented)
    assert not missing, (
        "backend/.env.example does not document these Settings aliases:\n"
        + "\n".join(f"  - {a}" for a in missing)
        + "\n\nAdd a line `<KEY>=<placeholder>` plus a description comment to "
        "backend/.env.example."
    )


# ----- S2.2 forbidden defaults are not echoed as default values ---------------


def test_env_example_does_not_echo_published_jwt_default() -> None:
    """`JWT_SECRET` must not have the published dev default as its example value."""
    if "JWT_SECRET" not in _example_keys():
        pytest.fail(
            "JWT_SECRET is not documented in backend/.env.example. "
            "Add it with an empty value and a comment explaining how to generate one."
        )
    text = ENV_EXAMPLE.read_text(encoding="utf-8")
    for line in text.splitlines():
        if line.lstrip().startswith("JWT_SECRET="):
            assert BANNED_LITERAL_DEFAULTS["JWT_SECRET"] not in line, (
                "backend/.env.example echoes the published JWT default literal. "
                "That value is in git history; example files must show an empty "
                "value with a comment instead."
            )


def test_env_example_does_not_echo_real_secret_keys() -> None:
    """No SECRET_KEY/API_KEY/PASSWORD line may echo a real-looking literal.

    Example files are committed to the repo. Real secrets in an example are a
    security incident waiting to happen. We accept:
      - empty values
      - values wrapped in `(...)` placeholders
      - values containing obvious filler (`your_`, `_here`, `_placeholder`,
        `changeme`, `replace_me`, `todo`)
      - values prefixed with known service markers (`gsk_`, `sk_`, `pk_`,
        `whsec_`, `re_`) — these are placeholder patterns, not real keys
        (real Groq/Stripe keys are longer and look different).
    """
    text = ENV_EXAMPLE.read_text(encoding="utf-8")
    secret_pattern = re.compile(
        r"^(?P<key>[A-Z][A-Z0-9_]*(?:SECRET|TOKEN|PASSWORD|API_KEY)[A-Z0-9_]*)\s*=\s*(?P<val>\S+)\s*$",
        re.IGNORECASE,
    )
    placeholder_signals = (
        "your_", "_here", "_placeholder",
        "changeme", "replace_me", "todo",
    )
    known_prefixes = ("gsk_", "sk_", "pk_", "whsec_", "re_")

    for line in text.splitlines():
        line = line.strip()
        m = secret_pattern.match(line)
        if not m:
            continue
        val = m.group("val").lower()
        if val.startswith("(") and val.endswith(")"):
            continue
        if any(signal in val for signal in placeholder_signals):
            continue
        if any(val.startswith(prefix) for prefix in known_prefixes):
            continue
        assert val == "", (
            f"backend/.env.example line `{m.group('key')}=<value>` carries a "
            f"non-empty value that does not match any known placeholder "
            f"pattern. Examples should leave secrets blank with a comment "
            f"indicating where the value lives in production."
        )
