# Template: cambio SDD para corregir un hallazgo de la auditoría

> Copiar a `openspec/changes/<change-name>/proposal.md` y completar. Referencia: [`README.md`](./README.md) (plan de ataque), [`00-hallazgos.md`](./00-hallazgos.md) (detalle), [`90-catalogo-completo.md`](./90-catalogo-completo.md) (apéndice).

---

**Change name:** `fix-<hallazgo-id>-<slug-corto>`
**Hallazgo vinculado:** `<S1 | S2 | S3 | S4 | F1 | F2 | F3 | L1 | T1 | A<n>>` — enlace a la sección en `docs/audit/`
**Severidad:** `<P0 | P1 | P2 | P3>`
**Fase del plan de ataque:** `<0 | 1 | 2 | 3>`

## Por qué

<Una o dos frases: qué falla hoy y qué consecuencia tiene. Copiar la sección "Qué pasa" y "Por qué importa" del hallazgo, no reformular.>

## Alcance

- **Incluye:** <archivos y comportamientos que cambian>
- **No incluye:** <lo que explícitamente queda fuera y en qué hallazgo/tracked issue va>
- **Specs afectadas:** `<openspec/specs/<capability>/spec.md>` (agregar delta con `ADDED` / `MODIFIED` / `REMOVED`)

## Decisiones de diseño abiertas

- <La decisión que el fixer tiene que tomar y no puede inferir del código. Ej.: para S1, cómo se declara el entorno de producción; para L1, cuán estricto es el matching numérico sin producir falsos positivos.>

## Tareas

- [ ] <Tarea 1 — incluye su test en la misma tarea>
- [ ] <Tarea 2>
- [ ] <Tarea 3>

## Verificación

- [ ] Test que falla antes del cambio y pasa después: `<nombre del test>`
- [ ] Comando: `<pytest / npm test / curl>` y resultado esperado
- [ ] Escenario manual, si aplica: <qué observar>

## Notas

- Evidencia previa: análisis estático por lectura de código (`file:line`). **No se reprodujo contra un sistema en ejecución** — si el hallazgo no se pudo reproducir, dejarlo explícito acá.
- Riesgo de regresión: <qué test existente podría romperse y por qué>
