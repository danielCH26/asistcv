# Proposal: Sprint 1 — Match JD ↔ Perfil (Slice 1)

## Intent

Slice 1: pegar un JD y obtener match honesto (score, fortalezas, gaps, energía, reasoning). Habilita las métricas fundacionales (15 min → 2 min por evaluación; 80% acuerdo humano). Sprint 0.5 dejó todo el stack en producción — aquí solo el **delta**.

## Scope

### In Scope (delta, issues #14–#20)

| Issue | Estado | Delta |
|---|---|---|
| #15 LLM | ✔ hecho (Groq) | Cierre/linking (título viejo: Vertex) |
| #14 Schema | ◐ parcial | Migración: `vector(1024)` + HNSW + SQLModel |
| #17 Endpoint | ◐ parcial | Persistir JD (con embedding) + análisis; `GET /v1/analyses` |
| #16 Retrieval | ✖ sin empezar | Servicio retrieval pgvector; umbral de tamaño |
| #18 MCP | ◐ parcial | `backend_url` → Render; timeout 30→60 s; formatos |
| #19 Frontend | ✖ sin empezar | SvelteKit adapter-static: form JD, resultado, historial |
| #20 Tests | ◐ parcial (49) | e2e slice, anti-alucinación, snapshot prompts, retrieval |

### Out of Scope

Auth multi-usuario, billing, ingesta de perfil, CV adaptado / outreach / company research (Sprint 2+), deploy automatizado frontend.

## Capabilities

**New:**
- `match-analysis`: endpoint, persistencia, historial, MCP prod.
- `semantic-retrieval`: schema vectorial, embeddings persistidos, retrieval con fallback.
- `match-ui`: frontend estático del flujo match.

**Modified:** None (`openspec/specs/` vacío).

## Approach

1. Migración aditiva (vectores + HNSW); validar en Neon branch.
2. JD → embedding BGE-M3 → contexto: retrieval si el perfil supera umbral (definir en design); si no, perfil completo. Infra lista sin over-engineering.
3. Persistir JD + análisis; frontend consume `/v1/match` y `/v1/analyses`.

## Affected Areas

| Área | Impacto |
|---|---|
| `backend/alembic/`, `app/db/models.py` | Mod — vector(1024), HNSW |
| `backend/app/api/v1/`, `app/services/retrieval`, `tests/` | Mod/New — flujo match |
| `frontend/` | New — SvelteKit adapter-static |
| `mcp-adapter/.../config.py` | Mod — URL prod, 60 s |

## Risks

| Riesgo | Prob. | Mitigación |
|---|---|---|
| Diff >> 600 líneas (frontend) | Alta | Cadena de PRs; fallback: frontend post-sprint |
| Rate limits Groq/HF | Media | Backoff existente; mocks en CI |
| Cold starts Render (~50 s) | Media | Timeout MCP 60 s; UX con loading |
| Endpoint público sin auth | Media | API key simple (decisión en design) |
| Score inflado (R1 ROADMAP) | Media | Validación con JDs reales |

## Rollout

Orden: #14 → #16 → #17 (+#20 continuo) → #18 → #19. Feature Branch Chain (budget 600, ask-on-risk):

- **PR1** vectores + retrieval (#14, #16) ~350 l
- **PR2** persistencia + historial + tests (#17, #20) ~300 l
- **PR3** MCP producción (#18) ~60 l
- **PR4** frontend (#19) ~500 l — candidato a PR separado post-sprint

Forecast formal en sdd-tasks.

## Rollback Plan

Revert por PR; `alembic downgrade` (aditiva, sin pérdida; probar en Neon branch); frontend/MCP aditivos.

## Dependencies

Ninguna nueva — stack completo operativo desde Sprint 0.5.

## Success Criteria

- [ ] Migración up/down OK en Neon; HNSW presentes
- [ ] `/v1/match` persiste JD + análisis; `/v1/analyses` lista historial
- [ ] Retrieval con umbral documentado (perfil completo mientras chico)
- [ ] Frontend: JD → resultado + historial contra producción
- [ ] MCP → Render, timeout 60 s
- [ ] Tests e2e, anti-alucinación, snapshot prompts, retrieval — CI verde
- [ ] JDs reales evaluados (meta ROADMAP: 20); latencia registrada

## Next Steps

`sdd-tasks`: breakdown por issue + forecast de PRs encadenados.
