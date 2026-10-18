# Feature: Embeddings locales (free tier, sin tarjeta) — #101

## Decisión

Reemplazar HuggingFace Inference API (401 en prod, requiere tarjeta) por inferencia local con ONNX vía `fastembed`:

- **Modelo**: `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`
- **Dimensión**: 384 (antes 1024 con BGE-M3)
- **Cross-lingual**: entrenado con datos paralelos de 50+ idiomas — soporta CV-es ↔ JD-en
- **Runtime**: ONNX (~15MB), NO torch (1-2GB). Modelo 220MB en disco
- **Restricción**: Render free tier = 512MB RAM → este modelo es el más grande viable

## Specs

> **S1**: `LocalEmbeddingProvider` que implementa el Protocol `LLMProvider.generate_embedding` usando fastembed. Init lazy del modelo (se carga una vez). Sync→async vía `asyncio.to_thread` para no bloquear el event loop. Devuelve `Embedding(vector=..., model=settings.embedding_model)`.

> **S2**: Settings: `embedding_provider` (default `local`) + `embedding_model` (default `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`). `hf_embedding_model` queda deprecated. Factory: branch `local`.

> **S3**: Migración `025`: `Vector(1024)` → `Vector(384)` en profiles, job_descriptions, analyses, users_cvs. Los embeddings viejos se descartan (set NULL): el match ya re-embeddea on-demand cuando `embedding is NULL` o el modelo difiere. El snapshot del JD histórico queda sin vector (el análisis conserva score/razones en texto).

> **S4**: Unificar la comparación de modelo: match.py (y donde más) compara contra `settings.embedding_model` (no `hf_embedding_model`).

> **S5**: Dockerfile: precargar el modelo en build (bake) para no depender de descarga en cold start.

> **S6**: Tests: unitarios con mock de fastembed (CI no descarga modelo) + smoke test real marcado para correr local. Suite completa verde (pytest, ruff, mypy).

> **S7**: Docs: STACK.md, README/.env.example con nuevas env vars.

## Acceptance criteria

- [ ] `/v1/match` y `/v1/adaptations` funcionan con `EMBEDDING_PROVIDER=local` sin API keys de embeddings
- [ ] Migración 025 aplicable en Neon (prod) y en DB local de tests
- [ ] CI no descarga el modelo (mocks)
- [ ] Smoke test local con modelo real: vector 384-dim, es/en cross-lingual
- [ ] QA en prod post-deploy: match + adapt desde navegador

## Tasks

> **T1**: Provider + settings + factory + tests (test-first)

> **T2**: Migración 025 + models.py 384

> **T3**: Unificar comparaciones de modelo de embedding

> **T4**: Dockerfile bake + env docs

> **T5**: ✅ PR #104 abierta — CI 7/7 verde (suite completa autoritativa 2m09s, Docker build con bake OK, ruff, mypy). Smoke real local: 384 dims, sim es↔en 0.987

> **T6**: QA en prod (post-deploy, con el usuario)

## Log

- L1: Usuario confirma opción local (fastembed + paraphrase-multilingual-MiniLM-L12-v2) — "me gusta, vamos con esa opcion"
- L2: HF removido por requisito de tarjeta de crédito + free tier agotado (#101, #102 obsoleto)
- L3: Roadmap exige "stack 100% free tier (sin tarjeta)" — esta decisión lo restablece

## PIVOTE (2026-10-08): local → Gemini embeddings

- L4: PR #104 mergeada (847b809): provider local + migración 025 (384-dim) + resolved_embedding_model + Dockerfile bake. El mecanismo de re-embed on-demand y marker-mismatch queda instrumentado.
- L5: **Render free (512MB RAM / 0.1 CPU) NO aguanta la inferencia local**: mail de Render "se superaron los límites de la instancia"; el container se mató a mitad del primer match (JD embed primero) → navegador ve "Failed to fetch" sin CORS headers. QA S2 abortado.
- L6: Usuario elige **Gemini embeddings** (API key AI Studio gratis sin tarjeta): `gemini-embedding-001`, multilingüe top-tier, output_dimensionality ajustable → 768 dims. Container vuelve a ser liviano (sin inferencia local en prod).

## Tasks (pivote Gemini)

> **T7**: GeminiEmbeddingProvider (REST httpx como HF provider) + settings (EMBEDDING_PROVIDER=gemini default local queda para dev, GEMINI_API_KEY) + factory + tests mockeando httpx (test-first). taskType SEMANTIC_SIMILARITY para ambos lados (el producto ES similarity scoring).

> **T8**: Migración 026: vector(384) → vector(768) + models.py. El mecanismo de marker-mismatch ya lo hace barato (~1 CV en prod).

> **T9**: Dockerfile: quitar el bake de fastembed (prod no usa local) + .env.example + STACK.md.

> **T10**: Suite (CI autoritativa) + PR.

> **T11**: Usuario: GEMINI_API_KEY en Render + migración 026 en Neon + deploy.

> **T12**: ✅ QA en prod — match 200 con **score 75** cross-lingual (JD en inglés ↔ CV es), persistencia OK, UI mostrando resultado. Adapt: 402 PLAN_LIMIT_REACHED (cuota free agotada de la cuenta QA — working as designed, valida sanitización con código estructurado). Issue #101 CLOSED (auto por merge de #105); #102/#36/#37 cerrados también.
