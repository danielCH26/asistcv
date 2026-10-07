"""
RED tests for ROADMAP.md (S8 of feat-c8-docs-makefile).

Issue #51:
- ROADMAP.md:39 documents `POST /jobs/evaluate` — the actual endpoint is
  `POST /v1/match`.
- ROADMAP.md:41 documents MCP tools `evaluate_job`, `read_profile`,
  `update_profile` — the only existing ones are `ping`, `get_health`, and
  `evaluate_match`.
- ROADMAP.md:58 documents `POST /jobs/{evaluation_id}/adapt` — the actual
  endpoint is `POST /v1/adaptations`.
- ROADMAP.md:60 documents MCP tool `adapt_for_job` — does not exist.

These tests pin each advertised endpoint against the actual route table and
each advertised MCP tool against the actual MCP tool registry, so the
doc-vs-code drift cannot return silently.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ROADMAP = REPO_ROOT / "ROADMAP.md"
BACKEND_APP_DIR = REPO_ROOT / "backend" / "app"
MCP_ADAPTER_SRC = REPO_ROOT / "mcp-adapter" / "src"


def _read() -> str:
    assert ROADMAP.is_file(), f"ROADMAP.md not found at {ROADMAP}"
    return ROADMAP.read_text(encoding="utf-8")


def _actual_backend_routes() -> set[str]:
    """Walk backend/app and collect every `@router.<verb>(...)` path prefix."""
    routes: set[str] = set()
    if not BACKEND_APP_DIR.is_dir():
        return routes
    for py in BACKEND_APP_DIR.rglob("*.py"):
        text = py.read_text(encoding="utf-8", errors="ignore")
        # Find patterns like `prefix="/v1/match"` and route paths inside
        # `@router.<verb>("...")`.
        for m in re.finditer(r'prefix\s*=\s*["\']([^"\']+)["\']', text):
            routes.add(m.group(1))
        for m in re.finditer(
            r"@router\.(?:get|post|put|delete|patch)\(\s*[\"']([^\"']+)[\"']",
            text,
        ):
            routes.add(m.group(1))
    return routes


def _actual_mcp_tools() -> set[str]:
    """Read mcp-adapter/src and extract registered tool names."""
    tools: set[str] = set()
    if not MCP_ADAPTER_SRC.is_dir():
        return tools
    for py in MCP_ADAPTER_SRC.rglob("*.py"):
        text = py.read_text(encoding="utf-8", errors="ignore")
        for m in re.finditer(r'name\s*=\s*["\']([a-z_][a-z0-9_]*)["\']', text):
            tools.add(m.group(1))
        # Also catch `@server.list_tools()` registrations and tool decorators.
        for m in re.finditer(
            r"@server\.\w+\(\s*[\"']?([a-z_][a-z0-9_]*)[\"']?\s*\)", text,
        ):
            tools.add(m.group(1))
        for m in re.finditer(
            r"@mcp\.\w+\(\s*[\"']?([a-z_][a-z0-9_]*)[\"']?\s*\)", text,
        ):
            tools.add(m.group(1))
    return tools


# ----- S8.1 endpoint drift --------------------------------------------------


def test_roadmap_endpoints_exist_in_backend() -> None:
    """Every endpoint path mentioned in ROADMAP.md must exist in the backend.

    Routes in the backend are mounted with `prefix=settings.api_prefix`
    (which is `/v1`). The route table we collect shows paths WITHOUT the
    prefix; the doc may add it. So we look for an exact match in `actual`,
    a `/v1`-stripped equivalent, or a `/v1`-prefixed equivalent.
    """
    text = _read()
    advertised = set(re.findall(r"`(POST|GET|PUT|DELETE|PATCH)\s+(/[^\s`]+)`", text))
    advertised = {p for _, p in advertised}  # just the paths
    actual = _actual_backend_routes()

    # ROADMAP also references the API prefix `/v1` as a stem; allow it.
    advertised.discard("/v1")

    missing = []
    for path in sorted(advertised):
        # Accept: exact match, with-/without-`/v1` variants, and stem matches
        # that allow {param} placeholder drift between the two sides.
        candidates = {
            path,
            path.removeprefix("/v1"),
            path if path.startswith("/v1") else f"/v1{path}",
        }
        if any(c in actual for c in candidates):
            continue
        if any(
            route == c
            or route.startswith(c + "/")
            or c.startswith(route + "/")
            for c in candidates
            for route in actual
        ):
            continue
        missing.append(path)

    assert not missing, (
        "ROADMAP.md advertises endpoints that don't exist in the backend:\n"
        + "\n".join(f"  - {p}" for p in missing)
        + f"\nActual backend routes: {sorted(actual)}"
    )


# ----- S8.2 MCP tool drift ---------------------------------------------------


def test_roadmap_mcp_tools_exist_in_adapter() -> None:
    """Every MCP tool name mentioned in ROADMAP.md must exist in the adapter."""
    text = _read()
    advertised = set(re.findall(r"`([a-z_][a-z0-9_]{2,})`", text))
    actual = _actual_mcp_tools()

    # Heuristic: only flag tools that appear in an MCP-related paragraph.
    # Look for tool names that show up in a sentence that contains "MCP" or
    # "tool" within ~80 chars of the name.
    suspicious: list[str] = []
    for name in sorted(advertised):
        if name in actual:
            continue
        # Look at the surrounding context in the doc.
        for match in re.finditer(re.escape(f"`{name}`"), text):
            start = max(0, match.start() - 80)
            end = min(len(text), match.end() + 80)
            context = text[start:end].lower()
            if "mcp" in context or "tool" in context:
                suspicious.append(name)
                break

    assert not suspicious, (
        "ROADMAP.md advertises MCP tools that don't exist in mcp-adapter:\n"
        + "\n".join(f"  - {n}" for n in suspicious)
        + f"\nActual MCP tools: {sorted(actual)}"
    )
