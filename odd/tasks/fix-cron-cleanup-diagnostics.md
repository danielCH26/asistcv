# Feature: Cron cleanup diagnostics (adaptations + audit retention)

## Specs

> **S1**: "Actualmente tengo otro agente realizando la migracion de resend a clerk para la autenticacion, Arregla lo que no tenga que ver con esa parte, el proyecto ya esta desplegado, aun no toquemos la parte de lemons queezy"

Restricción de scope heredada de la petición: fuera de la migración Resend → Clerk
(`auth.py`, email, refresh tokens) y fuera de Lemon Squeezy / billing.

## Problema

Las tres corinas de limpieza fallan en cada corrida, y una de ellas es
indiagnosticable:

- `adaptation-sweeper`: **100 de 100 corridas fallidas** desde al menos
  2026-10-01 (~4 por día × 20 días), cadencia de 15 minutos.
- `refresh-token-sweeper`: falla (datos de auth → fuera de scope de este
  slice, se reporta al agente de Clerk).
- `Audit Retention Cleanup`: falla con `401 {"code":"UNAUTHORIZED",
  "message":"Invalid cleanup token"}` visible en el log.

Dos causas distintas, ambas verificadas contra el servicio desplegado:

1. **Credencial ausente en el repositorio.** GitHub tiene solo
   `GROQ_API_KEY`, `HF_TOKEN` y `NEON_DATABASE_URL`. Le faltan
   `BACKEND_API_KEY` (para `adaptation-sweeper`) y `AUDIT_CLEANUP_TOKEN`
   (para `audit-retention`), que sí existen en Render. El sweep manda un
   header `X-Backend-API-Key:` vacío y la API responde 401, porque el
   endpoint falla cerrado por diseño.
2. **El camino de error es código muerto.** El paso usa `curl -fsS`:
   con `-f`, curl aborta ante cualquier 4xx/5xx, y como Actions ejecuta
   `bash -e`, el script muere en esa línea con exit 22 **antes** de
   llegar a `echo "Response status"` y al `else` que reporta el fallo. El
   log real del repo es solo `Process completed with exit code 22`.

Efecto: `cv_adaptations` pending huérfanas y `audit_uploads` vencidas
crecen sin limpieza, en un servicio que ya pasó por una auditoría de
seguridad (#85, #87).

## Specs

> **S2**: El fallo de un sweeper tiene que nombrar la causa accionable
> (secret ausente, 401 por mismatch, 404 de ruta, 502/503 de cold start,
> fallo de transporte), nunca un exit code desnudo.

> **S3**: Un sweeper con credencial ausente no toca el servicio.

> **S4**: Un cold start de Render (502/503/504) no debe condenar un sweep
> cada 15 minutos; el cleanup es idempotente, así que reintentar es seguro.

> **S5**: El contrato no cambia: mismos endpoints, mismo mecanismo de auth,
> misma condición de éxito (HTTP 200). No hay cambio de API.

## Tasks

- [x] **T1** — Reproducir el defecto con el script exacto de `main` contra un
  stub local 401: RED = exit 22 sin línea de status.
- [x] **T2** — `adaptation-sweeper.yml`: guard de secret ausente, captura de
  status + body, anotaciones por causa, retry con backoff solo en
  502/503/504, `timeout-minutes`, `permissions: {}`, parse con `python3`.
- [x] **T3** — `audit-retention.yml`: mismo tratamiento, con su propio
  mecanismo (token en el body) y su campo (`deleted_count`).
- [x] **T4** — `docs/DEPLOY.md`: documentar el par credential en los dos
  lados (Render **y** GitHub), corregir la afirmación de que los tres
  sweepers usan el header, y agregar entradas de troubleshooting.
- [x] **T5** — Verificar: matriz de 8 casos contra stub (secret ausente,
  401, 404, 200, cold start), `actionlint`, y sin POST contra producción.
- [ ] **T6** — Cargar los dos secrets en GitHub (requiere el valor de
  Render: lo ejecuta el maintainer).

## Acceptance criteria

- [x] Ningún camino de fallo termina en exit 22 sin diagnóstico
- [x] Cada status no-200 posible produce una explicación accionable
- [x] Secret ausente ⇒ no hay request al servicio
- [x] `actionlint` limpio en los dos archivos
- [x] Éxito (200) reporta el número de filas borradas
- [ ] Los tres sweepers en verde (depende de T6)

## Verificación

| Caso | Resultado |
|---|---|
| RED: script de `main` vs 401 | exit 22, sin línea de status (reproduce el log de prod) |
| Secret ausente (ambos) | `Missing secret`, exit 1, sin request |
| 401 (ambos) | status + body + causa, exit 1 |
| 404 | status + body + causa, exit 1 |
| 200 (ambos) | exit 0 + filas borradas |
| Cold start 502→502→200 | reintenta y termina en 200 |

## Log

- L1: "Arregla lo que no tenga que ver con esa parte [migración Resend →
  Clerk], el proyecto ya esta desplegado, aun no toquemos la parte de
  lemons queezy"
- L2: `refresh-token-sweeper.yml` tiene el mismo defecto de `-f` y el
  mismo secret ausente, pero su tabla (`users_refresh_tokens`) es dato de
  auth: **no se toca acá**, se reporta al agente de Clerk.
- L3: No se rota `BACKEND_API_KEY`: `mcp-adapter/src/asistcv_mcp/http_client.py`
  la manda como `Authorization: Bearer` contra `/v1`, así que rotarla sin
  actualizar ese lado rompe el adapter. La corrección es copiar el valor
  existente.
- L4: Se mantiene cada workflow autocontenido (shell duplicado ~20 líneas)
  en vez de una composite action, porque las composites exigen `checkout`
  y estos jobs no necesitan el repo. Beneficio: cada archivo se puede
  tirar y rehacer solo.
- L5: `set -e` queda fuera a propósito; el script decide su propio código
  de salida a partir del status HTTP.