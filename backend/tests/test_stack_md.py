"""
RED tests for STACK.md (S9 of feat-c8-docs-makefile).

Issue #51: STACK.md:27 (and many more) say the backend deploys to
HuggingFace Spaces. The actual deploy is Render (#41).

These tests pin the deploy destination table and the topology narrative.
"""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
STACK = REPO_ROOT / "STACK.md"


def _read() -> str:
    assert STACK.is_file(), f"STACK.md not found at {STACK}"
    return STACK.read_text(encoding="utf-8")


def _normalize(text: str) -> str:
    return text.lower()


def test_stack_md_backend_row_is_render() -> None:
    """The TL;DR stack table's Backend row must name Render, not HF Spaces."""
    text = _normalize(_read())
    # The Backend row in the TL;DR table. Look for the first row that has
    # "backend" in column 1 — it should not have "huggingface spaces" in
    # column 3.
    backend_row = ""
    for raw in text.splitlines():
        if raw.startswith("|") and "backend" in raw and "fastapi" in raw:
            backend_row = raw
            break
    assert backend_row, "STACK.md has no Backend row in the TL;DR table"
    assert "render" in backend_row, (
        f"STACK.md Backend row still names a non-Render destination:\n"
        f"  {backend_row}\n"
        f"The actual deploy is Render (issue #41)."
    )
    assert "huggingface spaces" not in backend_row and "hf spaces" not in backend_row, (
        f"STACK.md Backend row still says HuggingFace Spaces:\n  {backend_row}"
    )


def test_stack_md_topology_says_render() -> None:
    """The 'Topología' narrative must name Render for the backend, not HF Spaces."""
    text = _normalize(_read())
    # Find the Topología section.
    in_topo = False
    lines = []
    for raw in text.splitlines():
        if raw.startswith("## topolog"):
            in_topo = True
            continue
        if in_topo and raw.startswith("## "):
            break
        if in_topo:
            lines.append(raw)
    body = "\n".join(lines).strip()
    assert body, "STACK.md has no Topología section"
    # The section may legitimately reference HF Inference (embeddings), but the
    # backend hosting must be Render.
    assert "render" in body, (
        "STACK.md 'Topología' section does not mention Render as the backend "
        "host. Issue #41 deployed to Render.\n\n"
        f"Section body:\n{body}"
    )
    # And it must not assert the backend is hosted on HF Spaces.
    assert "backend" not in body or "desplegado en render" in body or "deploy a render" in body, (
        f"STACK.md 'Topología' still claims HF Spaces hosts the backend:\n{body}"
    )


def test_stack_md_secrets_are_render_not_hf_spaces() -> None:
    """The Secretos section must reference Render (where runtime secrets live),
    not HuggingFace Spaces."""
    text = _normalize(_read())
    # Find the Secretos section. The decision sections live at level 3 (###).
    lines = []
    in_secrets = False
    for raw in text.splitlines():
        if in_secrets:
            # End at next level-3 / 2/4 heading.
            if raw.startswith("### ") or raw.startswith("## "):
                break
            lines.append(raw)
            continue
        if raw.startswith("### secretos") or raw.startswith("## secretos"):
            in_secrets = True
    body = "\n".join(lines).strip()
    assert body, "STACK.md has no Secretos section"
    assert "render" in body, (
        f"STACK.md 'Secretos' section does not mention Render. Runtime "
        f"secrets live in the Render dashboard for the backend service.\n"
        f"Section body:\n{body}"
    )
