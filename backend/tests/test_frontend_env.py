"""
RED tests for frontend/.env.example (S4 of feat-c8-docs-makefile).

Issue #51: frontend/.env.example:9 documents `PUBLIC_BACKEND_API_KEY`, but
the build guard `frontend/scripts/check-env.mjs` and ci.yml:113-116 treat any
`PUBLIC_*_API_KEY` as a violation that breaks the build.

We assert the example has no such entry, AND that running check-env.mjs with the
example values produces exit 0 (no violations).
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_ENV = REPO_ROOT / "frontend" / ".env.example"
FRONTEND_CHECK = REPO_ROOT / "frontend" / "scripts" / "check-env.mjs"


def _public_api_key_lines() -> list[str]:
    """Return any lines in frontend/.env.example whose key matches PUBLIC_*_API_KEY."""
    assert FRONTEND_ENV.is_file(), f"frontend/.env.example not found at {FRONTEND_ENV}"
    pattern = re.compile(r"^PUBLIC_[A-Z0-9_]*_API_KEY\b", re.IGNORECASE)
    hits: list[str] = []
    for line in FRONTEND_ENV.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("#"):
            continue
        if pattern.search(line):
            hits.append(line)
    return hits


def test_frontend_env_no_public_api_key() -> None:
    """frontend/.env.example must not declare any PUBLIC_*_API_KEY entry.

    SvelteKit strips/forbids public env vars named *_API_KEY (the build
    script treats them as a security incident waiting to happen).
    """
    bad = _public_api_key_lines()
    assert not bad, (
        f"frontend/.env.example declares PUBLIC_*_API_KEY entries that the "
        "SvelteKit build guard rejects. Remove them.\n"
        + "\n".join(f"  - {l}" for l in bad)
    )


@pytest.mark.skipif(
    not shutil.which("node"),
    reason="node not installed; cannot run check-env.mjs",
)
def test_frontend_env_passes_check_env_guard(tmp_path: Path) -> None:
    """`node frontend/scripts/check-env.mjs` against the example must exit 0.

    Loads every active KEY=value line from frontend/.env.example into the
    subprocess env, then runs the guard. A passing run means the example is
    build-clean. A non-zero exit means the guard would block the build.
    """
    import os

    if not FRONTEND_CHECK.is_file():
        pytest.fail(f"check-env.mjs not found at {FRONTEND_CHECK}")

    # Build an env from the example file's KEY=value lines (active only,
    # not commented). We do this so the guard sees the same keys a user would
    # copy from the example.
    proc_env = os.environ.copy()
    for raw in FRONTEND_ENV.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^(?:export\s+)?([A-Z][A-Z0-9_]*)\s*=\s*(.*?)\s*$", line)
        if not m:
            continue
        key, value = m.group(1), m.group(2)
        if value.startswith("(") and value.endswith(")"):
            value = ""  # placeholder
        proc_env[key] = value

    result = subprocess.run(
        ["node", str(FRONTEND_CHECK)],
        cwd=REPO_ROOT / "frontend",
        env=proc_env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"frontend/scripts/check-env.mjs exited {result.returncode} against "
        f"frontend/.env.example values.\nstdout: {result.stdout}\n"
        f"stderr: {result.stderr}"
    )