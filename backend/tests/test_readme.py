"""
RED tests for README.md against the deployed product (S6 of feat-c8-docs-makefile).

Issue #51 lists these specific drifts:
- "Sprint 0 en curso" — Sprint 0 is closed
- License badge "Apache 2.0" vs body "TBD" — internal contradiction
- "Cloud: GCP (Cloud Run, Cloud SQL)" — backend is on Render
- "Match, adaptar CV + outreach, tracking pipeline" — only Match + Adaptación
  exist; Outreach and Tracking Pipeline are deferred to v2.0
- "make setup" / "make test" references — were stubs (now fixed in T1, but the
  README still says "Quick start" without mentioning the real targets).

These tests pin the *visible* text so the drift can't return.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
README = REPO_ROOT / "README.md"


def _read() -> str:
    assert README.is_file(), f"README.md not found at {README}"
    return README.read_text(encoding="utf-8")


def _normalize(text: str) -> str:
    """Lowercase, strip punctuation — used to compare the visible drift
    phrases against the body without false negatives on case.
    """
    return text.lower()


# ----- S6.1 status line -----------------------------------------------------


def test_readme_no_sprint_zero_in_progress() -> None:
    body = _normalize(_read())
    assert "sprint 0 en curso" not in body, (
        "README.md still says 'Sprint 0 en curso'. Sprint 0 is closed (see "
        "ROADMAP.md). Replace the status line with the current release target."
    )


# ----- S6.2 license consistency ---------------------------------------------


def test_readme_license_badge_and_body_match() -> None:
    """The license badge URL and the body text must name the same license."""
    text = _read()
    badge_match = re.search(r"License-([A-Za-z0-9._-]+)-", text)
    body_match = re.search(r"^##\s*Licencia\s*\n+(.+)$", text, re.MULTILINE)
    if not badge_match or not body_match:
        pytest.fail(
            "README.md is missing either the License badge or the Licencia "
            "section. Both are required for issue #51 to consider the drift "
            "closed."
        )
    badge_license = badge_match.group(1).lower()
    body_license = body_match.group(1).strip().lower()
    # Body must mention the same license family (Apache 2.0 vs MIT, etc.).
    badge_is_apache = badge_license.replace("-", "").startswith("apache")
    body_is_apache = "apache" in body_license
    assert badge_is_apache == body_is_apache, (
        f"License badge says {badge_license!r} but the body says {body_license!r}. "
        f"They must agree."
    )
    # Body must not say TBD.
    assert "tbd" not in body_license, (
        f"README.md Licencia section still says 'TBD'. Pick a license and "
        f"update both the badge and the body."
    )


# ----- S6.3 cloud deploy -----------------------------------------------------


def test_readme_no_gcp_runtime_claims() -> None:
    """No line in the README may claim the project runs on GCP."""
    text = _normalize(_read())
    bad_phrases = ("cloud run", "cloud sql", "artifact registry", "google cloud sdk")
    for phrase in bad_phrases:
        assert phrase not in text, (
            f"README.md mentions `{phrase}` but the backend is deployed to "
            f"Render and the frontend to Cloudflare Pages. Update the README "
            f"to reflect the actual cloud destinations."
        )


# ----- S6.4 capabilities -----------------------------------------------------


def test_readme_capabilities_match_codebase() -> None:
    """Each capability named in the README must exist in code.

    Outreach and Tracking Pipeline are not in the codebase yet — they are
    explicitly deferred to v2.0. The README must NOT name them as available.
    """
    text = _normalize(_read())
    forbidden = ("outreach", "tracking pipeline")
    for cap in forbidden:
        # We allow the words to appear inside a "Roadmap" or "Coming soon"
        # section, but not as a current capability.
        if cap not in text:
            continue
        # If present, the surrounding paragraph must use a deferred / planned
        # framing. We approximate by looking for the phrase alongside
        # "v2.0", "deferred", "coming", "planned", "roadmap".
        for paragraph in re.split(r"\n\s*\n", text):
            if cap not in paragraph:
                continue
            for signal in ("v2.0", "deferred", "coming", "planned", "roadmap", "futuro", "próximo"):
                if signal in paragraph:
                    break
            else:
                pytest.fail(
                    f"README.md mentions `{cap}` as if it were a current "
                    f"capability, but it is not implemented. Either remove "
                    f"the mention or add a 'deferred to v2.0' framing."
                )


# ----- S6.5 quick start -----------------------------------------------------


def test_readme_quick_start_uses_real_make_targets() -> None:
    """The Quick start section must not advertise fake targets."""
    text = _normalize(_read())
    # After T1, make setup/test/lint work. The README should mention the
    # working targets and not only individual sub-targets.
    assert "make setup" in text, (
        "README.md Quick start should mention `make setup` (now a real target)."
    )
    assert "make test" in text, (
        "README.md Quick start should mention `make test` (now a real target)."
    )
    # `make deploy` was removed in T1.
    assert "make deploy" not in text, (
        "README.md still references `make deploy`, but that target was removed "
        "in T1 (it was a GCP stub). Update the README to point at platform-"
        "managed deploy (Render + Cloudflare Pages)."
    )