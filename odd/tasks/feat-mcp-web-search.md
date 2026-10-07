# Feature: mcp-web-search

> **Issue**: #59 (milestone v1.0)
> **Branch**: `feat/mcp-web-search` (off main @ 4aa0c90)
> **Scope**: `web_search` MCP tool in the adapter, backed by Tavily, with exact-query TTL cache, structured logging, env plumbing, and provider-mocked tests. Backend untouched.

---

## Specs

### S1 — The `web_search` tool exists and returns a stable shape

Issue verbatim acceptance: *"`web_search(\"python frameworks 2026\")` devuelve 5 resultados con snippet + link + fecha."*

- Registered as `web_search` in `create_server()`: Spanish description (matching the existing tools' voice), input schema `{query: string (required), max_results: integer (default 5, min 1, max 10)}`.
- Returns a `json.dumps` string (TextContent) of: `{"query", "provider", "results": [{"title", "url", "content", "score", "published_date"}]}` — `published_date` is `str | null` (Tavily often omits it for general search; the shape must hold without it).
- Unknown tool dispatch stays an error; `max_results` coerced/clamped like the existing tools coerce args.

### S2 — Dedicated Tavily client with typed errors

New `src/asistcv_mcp/search_client.py`: `TavilyClient` (httpx.AsyncClient, own base URL `https://api.tavily.com`, `search(query, max_results)`), auth via `api_key` in the JSON body (canonical documented method). Error taxonomy mirroring `http_client`: `SearchError` base, `SearchAuthError` (401), `SearchRateLimitError` (429, keeps retry_after), `SearchTimeoutError`, `SearchConnectionError`. NOT reusing `BackendClient` (different base URL, body-auth vs Bearer, different semantics).

Missing `TAVILY_API_KEY` → clear `ValueError` at tool call: *"web_search no configurado: falta TAVILY_API_KEY."* `WEB_SEARCH_PROVIDER != "tavily"` → clear `ValueError` (Brave is v2.0 multi-provider, out of scope).

### S3 — Exact-query cache, TTL 1h, in-process

Issue decision (verbatim): *"¿Cache por query exacta o por query normalizada? Empezar exacta, simple."* — key = the literal query string, TTL 3600s, in-process dict with simple size cap (128; oldest-evicted). Cache hit skips the provider call and is visible in the log (`cache_hit=true`).

### S4 — Structured logging that cannot corrupt the stdio protocol

Every call logs one structlog event: `web_search_call` with `query, provider, latency_ms, num_results, cache_hit, error?`. **Constraint discovered in mapping:** the adapter's stdout IS the stdio MCP transport — logging there corrupts the protocol. Configure structlog (`logger_factory=WriteLoggerFactory(sys.stderr)` + JSONRenderer) so call logs land on **stderr as JSON** on the user's machine.

**Topology note (issue rewording):** the issue's *"Logs visibles en el dashboard de Render"* cannot apply to the adapter — topology is `client LLM ⇄ stdio ⇄ adapter (local) ⇄ HTTPS ⇄ backend (Render) ⇄ Tavily`; the adapter never touches Render. Render only sees backend logs, and the backend is a bystander here. Note this on the issue when closing.

### S5 — Env plumbing documented

`mcp-adapter/src/asistcv_mcp/config.py` gains `web_search_provider: str = "tavily"` and `tavily_api_key: str | None = None` (Settings auto-maps `WEB_SEARCH_PROVIDER` / `TAVILY_API_KEY`). `mcp-adapter/.env.example` documents both (the adapter already ships one). Backend env untouched — grep confirmed zero `tavily|web_search` references in `backend/`, and backend code never consumes search results (issue's env requirement is adapter-side).

### S6 — Date grounding ("grounding para fecha actual")

Static tool descriptions can't carry a fresh date (staleness), and MCP servers can't set the client's system prompt. Implementation: pass **server `instructions`** in the initialization handshake including today's date (computed at process start; stale only across midnight of a long-lived process). VERIFY against the installed `mcp` 2.2.0 that `create_initialization_options` accepts `instructions`; if unsupported, fall back to documenting that mainstream clients (Claude Desktop, Cursor) already inject the date, and keep the tool description mentioning that results may include dates.

### S7 — Provider-mocked tests verify the shape (issue verbatim)

*"Test que mockea el proveedor y verifica el shape de la respuesta."* Using the repo's conventions (`httpx.MockTransport` for the client layer, `AsyncMock` for the tool layer; pytest-asyncio auto; mypy-strict-compatible typing):
- shape test incl. `published_date: null` tolerance,
- cache hit does not re-call the provider, TTL expiry re-calls,
- 401 → `SearchAuthError`, 429 → `SearchRateLimitError` (with retry_after), generic 500 → `SearchError`,
- missing API key → `ValueError` with the documented message,
- unknown provider → `ValueError`,
- `list_tools()` exposes `web_search` with the expected schema.

---

## Tasks

| ID | Title | Route | Linked S# | Commit |
|---|---|---|---|---|
| T1 | RED: client-layer tests (shape via MockTransport, error taxonomy, key missing) → GREEN: `search_client.py` + TTL cache | direct | S2,S3,S7 | `feat(mcp): tavily search client with ttl cache and typed errors (T1 of #59)` |
| T2 | RED: tool/dispatch tests → GREEN: `tools.web_search` + `server.py` registration + config + `.env.example` | direct | S1,S5,S7 | `feat(mcp): web_search tool with env plumbing (T2 of #59)` |
| T3 | stderr JSON logging + date-grounding instructions (verify mcp 2.2.0) | direct | S4,S6 | `feat(mcp): stderr json logging and date grounding (T3 of #59)` |
| T4 | QA (adapter suite + ruff + backend suite untouched) + close + PR | direct | all | `test(mcp): full QA pass, closes #59` |

---

## Log

### L1 — User's verbatim request (2026-10-07)

> "continua"

(Within the standing directive: *"Sigue la ruta que consideres mas optima, pusheas, haces testeo qa cuando sea pertinente…"* — #59 is the last v1.0 feature after #61, per the agreed route.)

### L2 — Mapping findings that shaped the design (2026-10-07)

- Adapter-only: zero `tavily|web_search` hits in `backend/`; backend never consumes search results.
- Tool pattern: low-level `Server` with hand-written JSON schemas + `json.dumps` string results; plain async fns in `tools.py` with client as first arg.
- **stdout is the stdio transport** — structlog currently defaults to stdout; call logs MUST go to stderr (JSONRenderer) or they corrupt the protocol.
- **"Logs en Render" is architecturally impossible for this tool** — documented in S4; will be noted on the issue at close.
- No `respx` in dev deps; convention is `httpx.MockTransport` + `AsyncMock`. No `cachetools`; hand-rolled TTL dict. mypy `strict = true` — everything typed.
- Tavily: `POST https://api.tavily.com/search`, `api_key` in body, `published_date` often null for general topic — shape tolerant.
- Date grounding options ranked: server `instructions` (verify mcp 2.2.0 support) > do-nothing (clients inject date). Tool-description date rejected (staleness).

### L3 — Evidence / commits (appended as work progresses)

**T1 (S2,S3,S7 — client + cache) — DONE**
- RED: 11 tests failed on missing modules. GREEN: `search_client.py` (TavilyClient + taxonomía de errores) + `ttl_cache.py` (TTL con `now_fn` inyectable) + 2 campos en `config.py`.
- Fixture aprendizajes: `get_settings.cache_clear` no existe tras el monkeypatch (guard con getattr); el httpx inyectado necesita `base_url` propio para paths relativos.
- 11/11 · ruff · mypy strict ✅.

**T2+T3 (S1,S4,S5,S6,S7 — tool + logging + grounding) — DONE, con hallazgo mayor**
- **BUG DE PRODUCCIÓN descubierto y arreglado**: el lock de `mcp` es 2.2.0, que **eliminó la API de decoradores** del `Server` low-level (`@server.list_tools()` → AttributeError; los `type: ignore` lo ocultaban de mypy). El adapter **no podía ni construirse** con el lock actual. Además se descubrió que `uv run pytest` corría contra el **mcp del sistema** (el venv no tenía pytest — los dev-deps son extras; CI usa `uv sync --all-extras`) — los tests históricos nunca probaron el mcp del lock.
- Migración: `server.py` reescrito sobre **`MCPServer`** (el renombre de FastMCP en 2.x): tools declaradas con `@mcp.tool()` tipado (schemas generados por pydantic, `Field(ge=1, le=10)` para max_results), `run_stdio_async()` en `__main__`, todo mypy-strict sin ignores.
- **S6 date grounding**: `MCPServer(instructions=...)` acepta la fecha de hoy calculada al construir — verificado con test (`today in server.instructions`).
- **S4 logging**: structlog configurado con `WriteLoggerFactory(sys.stderr)` + `JSONRenderer` — el stdout es el canal stdio del protocolo; los eventos `web_search_call` (query, provider, latency_ms, num_results, cache_hit) van a stderr JSON.
- **S5 env**: `WEB_SEARCH_PROVIDER`/`TAVILY_API_KEY` en adapter config + `.env.example` documentadas.
- Verificado contra el mcp REAL del lock: 49/49 · ruff · mypy strict ✅.