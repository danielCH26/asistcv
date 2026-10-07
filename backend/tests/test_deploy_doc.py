"""
RED test for docs/DEPLOY.md CORS guidance (S5 of feat-c8-docs-makefile).

Issue #51: docs/DEPLOY.md:111-113 instructs the reader to set CORS_ORIGINS as
a CSV, but Settings.cors_origins (pydantic-settings) parses it as a JSON array.
Following the troubleshooting guidance breaks CORS in production.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DEPLOY_DOC = REPO_ROOT / "docs" / "DEPLOY.md"


def test_deploy_md_cors_instructions_are_json_array() -> None:
    """`docs/DEPLOY.md` must instruct CORS_ORIGINS as a JSON array, not CSV.

    We grep for lines that show `CORS_ORIGINS=...` with a plain comma-separated
    value. If such a line exists, the doc is teaching the user the wrong format
    and the app will reject the env var at startup.
    """
    assert DEPLOY_DOC.is_file(), f"docs/DEPLOY.md not found at {DEPLOY_DOC}"
    text = DEPLOY_DOC.read_text(encoding="utf-8")

    # Match `CORS_ORIGINS=host1,host2,...` (CSV style), excluding JSON-array
    # lines (which start with `[` or `'[`).
    csv_pattern = re.compile(
        r"CORS_ORIGINS\s*=\s*[\"']?[a-zA-Z]+://[^\"'\[\n]+,[^\"'\[\n]+",
        re.IGNORECASE,
    )

    bad_lines: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if csv_pattern.search(line):
            bad_lines.append(line)

    assert not bad_lines, (
        "docs/DEPLOY.md instructs CORS_ORIGINS as a CSV value, but "
        "Settings.cors_origins parses it as a JSON array (see app/core/config.py "
        "docstring). Update the troubleshooting example to use JSON-array "
        "syntax. Offending lines:\n"
        + "\n".join(f"  - {l}" for l in bad_lines)
    )


def test_deploy_md_cors_explanation_mentions_json_format() -> None:
    """The doc should explain why the format is JSON, not just show it."""
    assert DEPLOY_DOC.is_file()
    text = DEPLOY_DOC.read_text(encoding="utf-8")
    # Look for any paragraph near a CORS_ORIGINS= example that mentions JSON
    # or pydantic-settings.
    if "CORS_ORIGINS" not in text:
        return
    paragraphs = re.split(r"\n\s*\n", text)
    has_json_explanation = False
    for p in paragraphs:
        if "CORS_ORIGINS" in p and ("json" in p.lower() or "JSON" in p):
            has_json_explanation = True
            break
    assert has_json_explanation, (
        "docs/DEPLOY.md mentions CORS_ORIGINS but never explains the JSON-array "
        "format requirement. Add a sentence such as 'pydantic-settings parses "
        "CORS_ORIGINS as a JSON array, so the value must be a single string "
        "starting with [ and ending with ]'."
    )