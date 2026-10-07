"""
RED tests for the Makefile stubs (S1 of feat-c8-docs-makefile).

Issue #51: the project root Makefile advertises `setup`/`test`/`lint`/`deploy`
targets in README.md and /docs, but they only print `TODO` and exit 0 — so a
wrapper script can't tell whether the run actually did anything. We require:

- `setup` runs the real install commands (or exits non-zero loud on missing
  prereqs); no `TODO` placeholder text.
- `test` runs the real test runner; no `TODO` placeholder text.
- `lint` runs the real linter; no `TODO` placeholder text.
- `deploy` is either wired to a real documented command, or removed.

These tests are structural: they parse the Makefile text directly, so they
work without GNU make installed locally (CI runs them where make is on PATH).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MAKEFILE = REPO_ROOT / "Makefile"


def _read_makefile() -> str:
    assert MAKEFILE.is_file(), f"Makefile not found at {MAKEFILE}"
    return MAKEFILE.read_text(encoding="utf-8")


def _extract_target_body(text: str, target: str) -> str | None:
    """Return the body of a Makefile target (lines after the header until the
    next blank-line-separated block), or None if the target is not declared."""
    pattern = rf"^{re.escape(target)}\s*:(?!=)\s*(?:\n|.)*?(?=^\.PHONY|^[a-zA-Z_][\w-]*\s*:|\Z)"
    match = re.search(pattern, text, re.MULTILINE)
    if not match:
        return None
    return match.group(0)


# ----- S1.1 setup -----------------------------------------------------------


def test_make_setup_target_does_not_echo_todo() -> None:
    """`make setup` must not be a stub that just prints TODO and exits 0."""
    body = _extract_target_body(_read_makefile(), "setup")
    assert body is not None, "Makefile has no `setup:` target"
    assert "TODO" not in body, (
        f"`setup:` still echoes TODO. Replace with a real install command.\n"
        f"Target body:\n{body}"
    )


def test_make_setup_target_runs_real_commands() -> None:
    """`make setup` must run real install commands (uv sync or equivalent)."""
    body = _extract_target_body(_read_makefile(), "setup") or ""
    has_real_cmd = any(
        marker in body
        for marker in ("uv sync", "npm install", "uv pip install", "pip install")
    )
    assert has_real_cmd, (
        f"`setup:` does not invoke a real install command. Expected one of "
        f"`uv sync`, `npm install`, `uv pip install`, or `pip install`.\n"
        f"Target body:\n{body}"
    )


# ----- S1.2 test ------------------------------------------------------------


def test_make_test_target_does_not_echo_todo() -> None:
    """`make test` must not be a stub that just prints TODO and exits 0."""
    body = _extract_target_body(_read_makefile(), "test")
    assert body is not None, "Makefile has no `test:` target"
    assert "TODO" not in body, (
        f"`test:` still echoes TODO. Replace with the real test runner.\n"
        f"Target body:\n{body}"
    )


def test_make_test_target_runs_pytest() -> None:
    """`make test` must invoke pytest (backend) and/or vitest (frontend)."""
    body = _extract_target_body(_read_makefile(), "test") or ""
    has_real_runner = "pytest" in body or "vitest" in body or "npm run test" in body
    assert has_real_runner, (
        f"`test:` does not invoke pytest, vitest, or `npm run test`.\n"
        f"Target body:\n{body}"
    )


# ----- S1.3 lint ------------------------------------------------------------


def test_make_lint_target_does_not_echo_todo() -> None:
    """`make lint` must not be a stub that just prints TODO and exits 0."""
    body = _extract_target_body(_read_makefile(), "lint")
    assert body is not None, "Makefile has no `lint:` target"
    assert "TODO" not in body, (
        f"`lint:` still echoes TODO. Replace with the real linter.\n"
        f"Target body:\n{body}"
    )


def test_make_lint_target_runs_ruff() -> None:
    """`make lint` must invoke a real linter (ruff, eslint, etc)."""
    body = _extract_target_body(_read_makefile(), "lint") or ""
    has_real_linter = "ruff" in body or "eslint" in body or "npm run lint" in body
    assert has_real_linter, (
        f"`lint:` does not invoke ruff, eslint, or `npm run lint`.\n"
        f"Target body:\n{body}"
    )


# ----- S1.4 deploy ----------------------------------------------------------


def test_make_deploy_target_is_removed_or_real() -> None:
    """`make deploy` must be removed (it was a fake "deploy to GCP" stub) or
    wired to a real documented command. It MUST NOT advertise a deploy that
    does not happen — issue #51 named this drift.
    """
    body = _extract_target_body(_read_makefile(), "deploy")
    if body is None:
        # Target removed — that's acceptable per the issue decision.
        return
    # If still present, it must not be a stub.
    assert "TODO" not in body, (
        f"`deploy:` target still exists as a TODO echo. Per #51's decision,\n"
        f"either wire it to a real documented command or delete the target."
    )
    assert "GCP" not in body, (
        f"`deploy:` target still claims to deploy to GCP, but the backend is\n"
        f"deployed to Render and the frontend to Cloudflare Pages. Update or\n"
        f"remove this target."
    )