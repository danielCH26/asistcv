"""
RED tests for infra/README.md (S10 of feat-c8-docs-makefile).

Issue #51: infra/README.md describes Cloud Run, Cloud SQL, Artifact Registry,
Terraform and Cloud Build — none of which exist in this directory. The only
real artifacts are docker-compose.yml and .env.example.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
INFRA_README = REPO_ROOT / "infra" / "README.md"
INFRA_DIR = REPO_ROOT / "infra"


def _read() -> str:
    assert INFRA_README.is_file(), f"infra/README.md not found at {INFRA_README}"
    return INFRA_README.read_text(encoding="utf-8")


def _normalize(text: str) -> str:
    return text.lower()


def test_infra_readme_no_gcp_runtime_claims() -> None:
    """infra/README.md must not list GCP services as deployed infrastructure.

    Mentions inside a historical footnote (blockquote lines starting with `>`)
    are allowed per S10, as long as the operative sections don't claim them.
    """
    text = _normalize(_read())
    # Drop blockquote (historical footnote) lines before checking.
    operative_lines = [
        line for line in text.splitlines()
        if not line.lstrip().startswith(">")
    ]
    operative = "\n".join(operative_lines)
    bad_phrases = ("cloud run", "cloud sql", "artifact registry", "terraform", "cloud build")
    for phrase in bad_phrases:
        assert phrase not in operative, (
            f"infra/README.md mentions `{phrase}` outside a historical "
            f"footnote, but the project does not use that service. Remove it "
            f"or move the mention into the blockquote footnote."
        )


def test_infra_readme_describes_docker_compose() -> None:
    """The README should describe docker-compose.yml as the actual local infra."""
    text = _normalize(_read())
    assert "docker-compose" in text, (
        "infra/README.md does not mention docker-compose. The only real "
        "artifact in this directory is infra/docker-compose.yml."
    )


def test_infra_readme_describes_env_example() -> None:
    """The README should describe .env.example as the env template for local dev."""
    text = _normalize(_read())
    assert ".env.example" in text, (
        "infra/README.md does not mention .env.example. The directory ships "
        "infra/.env.example as the env template for local DB setup."
    )


def test_infra_readme_assets_referenced_exist() -> None:
    """Every asset/file mentioned in the README's 'Contents' section must exist."""
    text = _read()
    # Find lines under the Contents section.
    lines = text.splitlines()
    contents = []
    in_contents = False
    for line in lines:
        if re.match(r"^##\s+contents", line, re.IGNORECASE):
            in_contents = True
            continue
        if in_contents:
            if re.match(r"^##\s+", line):
                break
            contents.append(line)

    # Look for `path/to/file` or `something.yml` mentions.
    missing: list[str] = []
    for raw in contents:
        for file_match in re.finditer(r"`?([\w\-./]+\.(?:ya?ml|toml|yaml|json|sh))`?", raw):
            asset = file_match.group(1)
            if asset.endswith("file") or "/" not in asset:
                continue  # likely a description, not a path
            if not (INFRA_DIR / asset).is_file():
                missing.append(asset)
    assert not missing, (
        "infra/README.md references files that don't exist in infra/:\n"
        + "\n".join(f"  - {m}" for m in missing)
    )
