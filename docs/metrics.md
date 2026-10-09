# Métricas — AsistCV

> Documento vivo. Documenta las métricas del [documento fundacional](../job-search-assistant.md) con datos reales del uso del producto. **Política de honestidad: ningún número inflado** — si una métrica no tiene datos suficientes, se dice explícitamente y se documenta cómo se va a medir.

> Última actualización: 2026-10-09.

---

## Métricas primarias

### 1. 30+ aplicaciones con el sistema

- **Definición operativa**: cantidad de aplicaciones enviadas donde el CV fue adaptado o revisado con AsistCV. Se mide por conteo de adaptaciones aprobadas + usos de match con envío posterior (el autor lleva el registro personal de envíos).
- **Número real**: *sin datos suficientes aún* — el producto pasó a producción estable recién (octubre 2026, tras resolver #101); el autor registra sus aplicaciones manualmente.
- **Observaciones**: esta métrica requiere 30+ días de uso real del autor en su búsqueda. El pipeline técnico que la soporta está verificado: match 200 con score y persistencia en producción (2026-10-09, QA con score 75 cross-lingual).

### 2. 80% match accuracy vs decisión humana

- **Definición operativa**: de cada match con score ≥ umbral, el porcentaje donde la decisión humana (aplicar / no aplicar) coincide con la recomendación del sistema. Se mide comparando el historial de matches del autor contra sus aplicaciones reales.
- **Número real**: *sin datos suficientes aún* — requiere el registro de decisiones humanas contra los matches generados.
- **Observaciones**: el score honesto está diseñado para ser conservador (energía `low/medium/high` con razones explícitas). La calidad del matching subió con el pivote a `gemini-embedding-001` (líder multilingüe MTEB) tras los dos pivotes de #101; smoke local: similitud cross-lingual es↔en 0.987.

### 3. Tiempo de evaluación de JD: < 2 min vs 15 min manual

- **Definición operativa**: tiempo desde pegar la JD hasta tener el score con razones. Se mide con `duration_ms` del log del backend (request `/v1/match`).
- **Número real**: ✅ **~3.6s en producción** (2026-10-09: POST `/v1/match` → 200 con score 75, 3625ms incluyendo embedding Gemini + LLM Groq + persistencia Neon). La primera llamada tras cold start suma ~30-50s (Render free duerme tras 15 min de inactividad).
- **Observaciones**: **cumplida con 33x de margen** contra los ~15 min manuales. El tiempo humano restante es leer el resultado (~30s), no esperar al sistema.

### 4. 3+ entrevistas atribuibles

- **Definición operativa**: entrevistas obtenidas donde la aplicación fue adaptada/revisada con AsistCV. Se mide con el registro personal del autor (auto-reporte con timeline de aplicaciones).
- **Número real**: *sin datos suficientes aún* — depende del ciclo de entrevistas del autor.
- **Observaciones**: downstream de la métrica 1. El pipeline técnico está listo; la atribución es auto-reportada.

---

## Métricas secundarias

### Costo por aplicación

- **Definición operativa**: costo de infra + LLM dividido por aplicaciones con el sistema.
- **Número real**: **$0 de infra** (stack 100% free tier: Render free, Cloudflare Pages free, Neon free, Gemini API free, Groq free) — sin tarjeta de crédito. El costo marginal por aplicación es el tiempo de CPU incluido en el free tier.
- **Observaciones**: verificado en producción: el intento de inferencia local (fastembed) superó los límites de la instancia free de Render (#101 pivote 1) — la inferencia en el container no es viable; la API de embeddings gratuita sí.

### Latencia de respuesta

- **Definición operativa**: `duration_ms` por endpoint, del log del backend.
- **Números reales** (producción, 2026-10-09):
  - `/v1/match`: ~3.6s (embedding Gemini ~0.5-1s + Groq ~1-1.5s + DB ~0.2s)
  - `/health`: ~1.5ms
  - Cold start post-deploy o post-sleep: ~30-50s (limitación de Render free, documentada en STACK.md)
- **Observaciones**: el embedding es la llamada de red más barata del flujo; el LLM (Groq) domina la latencia del match. Para early adopters invitados uno-a-uno es aceptable; si v2.0 exige menos, el plan de Render con más CPU y Groq con modelos más rápidos son los palancas.

### Tasa de respuestas positivas

- **Definición operativa**: respuestas del reclutador / aplicaciones con respuesta vs enviadas. Requiere el tracking pipeline (deferido a v2.0) o auto-reporte del autor.
- **Número real**: *sin datos suficientes aún*.

### Calidad percibida de CV

- **Definición operativa**: feedback del usuario (o de reclutadores en el flujo consented) sobre los CVs adaptados. Requiere instrumentación de feedback (deferida).
- **Número real**: *sin datos suficientes aún*. El validador anti-alucinación garantiza que el CV adaptado no inventa skills/achievements (coverage 99%, tests bloquean en CI — issue #26).

---

## Estado de la instrumentación

| Métrica | Fuente de datos | Estado |
|---|---|---|
| Aplicaciones con el sistema | Registro manual del autor | ⏳ pendiente de uso real |
| Match accuracy | Historial + decisiones humanas | ⏳ pendiente |
| Tiempo de evaluación | `duration_ms` del backend log | ✅ instrumentada, 3.6s |
| Entrevistas atribuibles | Auto-reporte del autor | ⏳ pendiente |
| Costo | Free tiers + logs | ✅ instrumentada, $0 |
| Latencia | `duration_ms` del backend log | ✅ instrumentada |
| Respuestas positivas | Tracking pipeline (v2.0) | ⏳ diferida |
| Calidad percibida | Feedback (por instrumentar) | ⏳ diferida |

El monitoreo sistemático (Sentry, Plausible, dashboard de error rate) está planificado para v2.0 ([ROADMAP.md](../ROADMAP.md)).
