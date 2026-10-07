"""
RED tests for infra/.env.example (S3 of feat-c8-docs-makefile).

Issue #51: infra/.env.example uses port 5432 but infra/docker-compose.yml
publishes port 5433 and Settings.database_url also uses 5433. Copying the
example produces a connection failure.

We read both files live so the test fails if either drifts again.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
INFRA_ENV = REPO_ROOT / "infra" / ".env.example"
INFRA_DOCKER_COMPOSE = REPO_ROOT / "infra" / "docker-compose.yml"


def _published_db_port() -> int | None:
    """Return the host port the `db` service publishes in docker-compose.yml.

    Returns None if the service or port mapping is missing.
    """
    if not INFRA_DOCKER_COMPOSE.is_file():
        return None
    text = INFRA_DOCKER_COMPOSE.read_text(encoding="utf-8")
    # Find the `db:` service block, then the first ports entry of shape
    # `"HOST:CONTAINER"`.
    db_block = re.search(
        r"^\s*db\s*:(?:\n(?:\s+[^\n]*\n)+)",
        text,
        re.MULTILINE,
    )
    if not db_block:
        return None
    ports_line = re.search(r"-\s*\"(\d+):(\d+)\"", db_block.group(0))
    if not ports_line:
        return None
    return int(ports_line.group(1))


def _example_db_port() -> int | None:
    """Return the port from the DATABASE_URL line in infra/.env.example."""
    assert INFRA_ENV.is_file(), f"infra/.env.example not found at {INFRA_ENV}"
    for line in INFRA_ENV.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"DATABASE_URL\s*=\s*\S+?:(\d+)\s*/", line)
        if m:
            return int(m.group(1))
    return None


def test_infra_env_port_matches_docker_compose_published_port() -> None:
    """infra/.env.example DATABASE_URL port must equal docker-compose host port."""
    published = _published_db_port()
    assert published is not None, (
        "Could not find `db` service port mapping in infra/docker-compose.yml"
    )
    example = _example_db_port()
    assert example is not None, (
        "infra/.env.example has no DATABASE_URL line"
    )
    assert example == published, (
        f"infra/.env.example DATABASE_URL points at port {example}, but "
        f"docker-compose.yml publishes the db service on host port {published}. "
        f"Align them so the example works out of the box."
    )
