"""
RED tests for PROJECT.md (S7 of feat-c8-docs-makefile).

Issue #51: PROJECT.md:9 says "el próximo paso es arrancar Slice 1"; Slice 1
and Slice 2 are already merged. PROJECT.md:64-70 lists the free-tier migration
and the deploy as pending — both done (#38-#43, #41, #42). License says TBD
while README says Apache 2.0.

These tests pin the visible drift so it cannot return.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PROJECT = REPO_ROOT / "PROJECT.md"


def _read() -> str:
    assert PROJECT.is_file(), f"PROJECT.md not found at {PROJECT}"
    return PROJECT.read_text(encoding="utf-8")


def _normalize(text: str) -> str:
    return text.lower()


def test_project_md_no_pending_migration_items() -> None:
    """PROJECT.md must not mark the free-tier migration or deploy as pending.

    All items from issues #38–#43 (Neon setup, Groq/HF rewiring, GH Actions,
    HF Spaces deploy, Cloudflare Pages deploy, secrets setup) are merged.
    PROJECT.md must reflect that.
    """
    text = _normalize(_read())
    # The migration list (paraphrased — we check for the visible drift).
    forbidden_phrases = (
        "reescribir backend: settings + clientes llm",
        "provisionar neon postgres + pgvector",
        "ci/cd con github actions (build + deploy a hf spaces y cloudflare pages)",
        "deploy backend en huggingface spaces",
        "deploy frontend en cloudflare pages",  # in PR-cloudflare branch
        "validación end-to-end con credenciales reales",
        "proposal, specs, design e implementación del slice 1",
    )
    for phrase in forbidden_phrases:
        assert phrase not in text, (
            f"PROJECT.md still lists `{phrase}` as pending, but it was completed "
            "in issues #38–#43. Remove the line or mark it done."
        )


def test_project_md_no_arrancar_slice_1_as_next_step() -> None:
    """The 'Fase actual' / 'próximo paso' must not point at Slice 1 as next."""
    text = _normalize(_read())
    # Catch "arrancar slice 1", "arrancar el slice 1", "arrancar slice 2",
    # and the implicit version "próximo paso ... slice 1/2".
    forbidden_phrases = (
        "arrancar slice 1",
        "arrancar el slice 1",
        "arrancar slice 2",
        "arrancar el slice 2",
    )
    for phrase in forbidden_phrases:
        assert phrase not in text, (
            f"PROJECT.md still says the next step is `{phrase}`; Slices 1 and "
            f"2 are already merged. Update the 'Fase actual' line."
        )


def test_project_md_no_huggingface_spaces_runtime_claim() -> None:
    """PROJECT.md must not say backend deploys to HuggingFace Spaces."""
    text = _normalize(_read())
    assert "huggingface spaces" not in text, (
        "PROJECT.md mentions HuggingFace Spaces as the backend deploy, but "
        "the backend is deployed to Render. Update the stack table and "
        "narrative."
    )


def test_project_md_license_not_tbd() -> None:
    """PROJECT.md Licencia must name a license, not TBD."""
    text = _normalize(_read())
    # Join the Licencia section heading with its body so we capture the
    # paragraphs that follow the heading line.
    blocks = re.split(r"\n\s*\n", text)
    for i, block in enumerate(blocks):
        if block.startswith("## licencia"):
            # Concatenate this block and the next few blocks until the next
            # `## ` heading.
            j = i + 1
            section = [block]
            while j < len(blocks) and not blocks[j].startswith("## "):
                section.append(blocks[j])
                j += 1
            joined = "\n".join(section)
            if "tbd" in joined:
                pytest.fail(
                    "PROJECT.md Licencia section still says 'TBD'. Pick a "
                    "license (the README badge already says Apache 2.0)."
                )
            return
    pytest.fail("PROJECT.md has no Licencia section")
