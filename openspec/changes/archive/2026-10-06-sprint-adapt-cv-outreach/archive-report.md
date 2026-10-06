# Archive Report: sprint-adapt-cv-outreach

## Summary

**Change**: sprint-adapt-cv-outreach (Slice A)
**Closed**: 2026-10-06
**Commits on main**: `aaf8cf9` (PR1 foundation), `b426374` (PR2a service layer), `9fca36c` (PR2b endpoints + runner + sweeper), `12dc7da` (PR3 frontend)
**Remediation commits**: `cd0d38d` (#62), `317d8dc` (#73), `7f34efb` (#74), `602d324` (#75), `36f7f69` (#50 post-commit RLS)

## Por qué se verificó ahora

Este change llevaba meses abierto con `tasks.md` en **0/37** y sin `verify-report`.
La causa: **se implementó sin pasar por la fase `apply`** — el trabajo entró como cuatro
commits directos, así que los checkboxes nunca se marcaron.

`docs/audit/PLAN.md` dejó la decisión abierta: "queda abierto decidir si se archiva o se
verifica primero". Se verificó primero.

## Verificación

**Veredicto: PASS WITH FINDINGS** — 10 de 21 requirements `MET`, 11 `PARTIAL`, 0 `NOT MET`.

Detalle completo en [`verify-report.md`](./verify-report.md).

| Nivel | N | Resumen |
|---|---|---|
| CRITICAL | 3 | `content_version` inexistente (#81) · `sanitize_jd` nunca implementado (#82) · `jd_text` valida ≥1 y no ≥50 (#83) |
| WARNING | 11 | Divergencia de contrato de respuesta, `outreach`/`brief` ausentes en vez de `null`, `adaptation_enabled` en `False` por defecto, alias del validador admite 23 de 26 letras sueltas (#84) |

**Los 3 CRITICAL están en la misma capa**: el contrato de datos de PR2. Es exactamente la
capa que se saltó al implementar por commits directos en vez de por la fase `apply`.

## Reconciliación de tareas

| Estado | N |
|---|---|
| `SHIPPED` | 18 |
| `PARTIAL` | 15 |
| `NOT SHIPPED` | 4 |
| `SUPERSEDED` | 2 |
| `UNVERIFIABLE` | 1 |

Los checkboxes de `tasks.md` **no se tocaron**: marcarlos todos habría sido tan falso como
dejarlos en cero. La tabla de la sección "Estado real verificado" es la autoritativa.

Lo que no salió: los tests de paridad match/audit (PR2.1), el E2E (PR2.18), y **todos los
tests de frontend de PR3** — componente (PR3.8) y fases de polling (PR3.10). La capa de
frontend se verificó con `npm run test` y `svelte-check`, no con los tests que el change
prometía.

## Evidencia de tests al cierre

| Suite | Resultado |
|---|---|
| Tests de adaptación (5 archivos) | 152 passed |
| Backend completo | 484 passed · 1 failed · 1 skipped · 1 xfailed |
| Frontend | 48/48 |
| `svelte-check` | 0 errors · 1 warning preexistente |

El único fallo es `test_cv_storage` (separadores POSIX en Windows, preexistente, verificado
con el árbol limpio). El `xfail` es el contrato multipart de #77.

## Delta specs: **NO sincronizadas**

Sprint 2 sincronizó sus delta specs a `openspec/specs/`. **Este change no.**

Motivo: la verificación encontró que los specs **no describen la API desplegada** — la ruta
del listado, el cuerpo del 402, el código del 404, el `poll_url` y los nombres de campo
difieren todos. Promoverlos a canónicos los convertiría en la referencia equivocada para
cualquiera que escriba código nuevo contra ellos.

Se sincronizan cuando **#84** cierre la decisión de cuál es el contrato. Queda registrado
aquí para que no se pierda.

## Seguimientos abiertos (NO arreglar acá)

| Issue | Qué |
|---|---|
| #81 | `content_version` no existe; invalidación de caché tautológica, y su test es tautológico |
| #82 | `sanitize_jd` nunca implementado — `cvA-R4` sin fulfilling |
| #83 | `jd_text` valida ≥1 carácter en vez de ≥50 |
| #84 | 11 WARNING, incluido que `adaptation_enabled` tiene default `False` |
| #77 | `POST /v1/recruiter/candidates` 422 — el flujo de recruiter no arranca |
| #78 | `recruiter_consent` toma la identidad de un campo del body |
| #79 | `Analysis.strengths` anotado `dict` guardando listas |
| #80 | `test_cv_storage` falla en Windows |

## Archive Contents

- `proposal.md` ✅
- `design.md` ✅
- `specs/cv-adaptation/spec.md` ✅ (**no sincronizado**, ver arriba)
- `specs/adaptation-billing/spec.md` ✅ (**no sincronizado**)
- `specs/adaptation-experience/spec.md` ✅ (**no sincronizado**)
- `specs/cv-management/spec.md` ✅ (**no sincronizado**)
- `tasks.md` ✅ (37 tareas, con tabla de estado real)
- `verify-report.md` ✅ (**nuevo**)

## Estado del ciclo SDD

El change queda **cerrado con hallazgos, no limpio**. El código está en `main` y no se puede
deshacer; lo que falta son correcciones de correctitud, que son trabajo nuevo y ya están
rastreadas en #81–#84.

El `verify-report.md` está escrito en inglés mientras el resto de los artefactos del repo
están en español. Es una inconsistencia de idioma pendiente de resolver.