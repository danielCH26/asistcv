# Plan de remediación — Auditoría 2026-09-29

> **Estado:** plan aprobado, issues creadas (#44–#51). Fase 0 en curso.
> **Knowledge base:** [`README.md`](./README.md) · [`00-hallazgos.md`](./00-hallazgos.md) · [`90-catalogo-completo.md`](./90-catalogo-completo.md)
> **Preflight de sesión:** `execution_mode: auto` · `artifact_store: hybrid` · `delivery_strategy: auto-chain` · `review_budget_lines: 800`

---

## Por qué agrupar por cluster y no por bug

Los hallazgos de la auditoría no son 12 bugs sueltos: son **8 clases raíz**. La regla de triage dice que dos o más hallazgos que comparten una raíz se resuelven con **un** fix que los cierra a todos, y que N hallazgos nunca justifican N parches sueltos.

| Cluster | Raíz | Hallazgos | Issues |
|---|---|---|---|
| **C1** | Secretos de configuración sin guardia fail-closed | S1, S2 | #44 |
| **C2** | El capability token del funnel tratado como autenticación | S3, S4 | #45 |
| **C3** | El resolver de auth no devuelve la forma que el handler espera | F1 | #46 |
| **C4** | Degradación silenciosa en el pipeline de audit | F2 | #47 |
| **C5** | Ciclo de vida del contexto RLS (bind + commit) | F3 | #48 |
| **C6** | Contrato de honestidad verificado solo léxicamente | L1 | #49 |
| **C7** | Puntos ciegos de test/CI que enmascaran C1–C5 | T1 | #50 |
| **C8** | Docs y andamiaje describen el producto anterior | D1–D3 | #51 |

**C7 es una precondición de las demás.** Sin `permissions:` explícitos en los workflows y sin tests de frontend en CI, cualquier fix de C1–C6 puede revertirse en silencio. Por eso, aunque C7 va en Fase 2, su parte de *workflow permissions* es trivial y conviene no demorarla.

---

## Orden de ejecución

El orden **no** es por severidad individual: es por radio de daño y dependencia ascendente. Un fix de auth mal aplicado invalida cualquier test que escribamos encima.

### Fase 0 — Seguridad (P0)

| Orden | Cluster | Issue | Depende de | Accionable por |
|---|---|---|---|---|
| 0.1 | — | **Rotación de `JWT_SECRET` en Render** | — | ⚠️ **Solo el maintainer** (dashboard) |
| 0.2 | C1 | Fail-closed para `JWT_SECRET` | — | Código |
| 0.3 | C1 | Fail-closed para `BACKEND_API_KEY` en prod | 0.2 | Código |
| 0.4 | C2 | `claim_audit` exige caller autenticado | — | Código |
| 0.5 | C2 | Router interno separado (mata el montaje duplicado) | 0.4 | Código |
| 0.6 | C2 | Kill-switch a los GET de adaptaciones | — | Código |
| 0.7 | C2 | Resolver `_encrypted` (implementar o renombrar) | — | **Decisión de diseño** |

**0.1 no es código.** Es cambiar una env var en el dashboard de Render. Está confirmada como explotada (un access token firmado con la clave por defecto del repo fue aceptado contra el despliegue real). El fix de código en 0.2 previene que se repita; **solo la rotación cierra la vulnerabilidad actual**, porque el valor viejo queda público en el historial de git para siempre.

### Fase 1 — Bugs funcionales (P0/P1)

| Orden | Cluster | Issue | Nota |
|---|---|---|---|
| 1.1 | C3 | Billing: resolver los atributos correctos | Incluye implementar verificación de email real — sin eso la guarda es insatisfacible |
| 1.2 | C4 | `jd_directed` manda el CV real | Superficie pública sin registro; el feature no funciona |
| 1.3 | C5 | Runner bindea contexto RLS | Cierra la cuota no consumida (planes pagos ilimitados) |
| 1.4 | C5 | Reconciliar índice único / caché / sweeper | **Decisión de diseño** (ver abajo) |

### Fase 2 — Honestidad + red de seguridad (P1)

| Orden | Cluster | Issue | Nota |
|---|---|---|---|
| 2.1 | C7 | Tests frontend en CI | Barato, alto valor |
| 2.2 | C7 | Test RLS per-user vía DI real | Requiere aislar el hook global de `conftest` |
| 2.3 | C7 | `permissions: contents: read` en los 3 workflows | Trivial |
| 2.4 | C6 | Validador verifica métricas numéricas | **Decisión de diseño** (tolerancia de redondeo) |

### Fase 3 — Docs y deuda (P2)

| Orden | Cluster | Issue | Nota |
|---|---|---|---|
| 3.1 | C8 | `Makefile`: implementar o borrar los stubs | Coordinar con #34, #33 |
| 3.2 | C8 | Reescribir docs contra el producto real | Va **último** a propósito: documentar antes de congelar el comportamiento produce docs que vuelven a quedar viejas |
| 3.3 | C8 | Completar `.env.example`, corregir puerto y formato CORS | |
| 3.4 | C8 | Eliminar dead code (deletion-heavy) | PR dedicado |

---

## Decisiones de diseño pendientes

Estas son del maintainer. No las tomo yo.

1. **Cómo se declara "producción"** para los guards fail-closed (afecta #44). Opción A: flag explícito de entorno. Opción B: fail-closed por defecto, que obliga a definir el secret en el `.env` de dev local. B es más segura pero más invasiva para el flujo local.
2. **`jd_text_encrypted`**: implementar el cifrado o renombrar la columna (afecta #45). Renombrar es más barato y honesto; cifrar cumple lo que el nombre promete.
3. **Tolerancia numérica del validador** (afecta #49). Verificar el número exacto rompe por redondeo y reformato; matching por valor necesita normalización de moneda y separadores. La vía segura es *rechazar* si no aparece en alguna forma normalizada y dejar que el reintento con instrucción estricta lo resuelva.
4. **Ciclo de vida de la adaptación** (afecta #48): extender la caché a 90 días, hacer que el sweeper elimine `completed` más viejos que la ventana de caché, o cambiar el índice único para incluir `created_at`.
5. **Outreach y Tracking Pipeline**: ¿entran al roadmap o salen de la lista de capacidades del README? Hoy el README anuncia tres y solo existen dos (afecta #51).

---

## Criterio de cierre

Una issue se cierra contra **tests nombrados**, no contra promesas. Cada fix de este plan trae sus tests en el issue correspondiente. Además, como la auditoría es análisis estático, un hallazgo se considera cerrado solo cuando:

1. existe un test que **falla contra el código actual** y pasa contra el fix, y
2. en el caso de #44, la verificación confirma que el token firmado con la clave vieja devuelve 401 contra el despliegue real.

Regla adicional: si un test escrito contra el mecanismo descrito en la issue **pasa** sobre `main` sin modificar, el diagnóstico es incorrecto aunque el síntoma sea real — hay que reforzar el test hasta que ataque la superficie verdadera.

---

## Lo que NO cubre este plan

- Los ~70 hallazgos del apéndice (`90-catalogo-completo.md`) están catalogados pero fuera del alcance de las 4 fases. Se priorizan si aparece un incidente.
- El change activo `sprint-adapt-cv-outreach` está effectively completo en código (4 PRs mergeados) pero muestra 0/37 tareas y no tiene `verify-report`. Queda abierto decidir si se archiva o se verifica primero.
- No se verificó en producción nada más allá de la configuración de auth y #44. Los hallazgos de Fase 1–3 están sin verificar contra el sistema corriendo.
