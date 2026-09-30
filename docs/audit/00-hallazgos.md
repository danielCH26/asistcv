# Hallazgos detallados

> **Naturaleza de la evidencia:** análisis estático por lectura de código. Las referencias `file:line` son verificables, pero **ningún hallazgo fue reproducido contra un sistema en ejecución**. Ver la nota de alcance en [`README.md`](./README.md).

Cada sección tiene la misma estructura: **Severidad**, **Ubicación**, **Qué pasa**, **Por qué importa**, **Estrategia de fix**, **Verificación**.

---

# Fase 0 — Seguridad (P0)

## S1 — `jwt_secret` con default público y sin guarda

> 🔴 **CONFIRMADO EXPLOTADO EN PRODUCCIÓN (2026-09-29).** Se firmó un access token con `dev-secret-change-in-production` y el backend desplegado (`https://asistcv-backend.onrender.com`) lo aceptó, devolviendo datos reales del usuario `id=1`. No es un riesgo latente: es una cuenta abierta **ahora**. Ver detalle en [`README.md` → Verificación en producción](./README.md#verificación-en-producción).

**Severidad:** P0 — exploited

**Ubicación**
- `backend/app/core/config.py:52` — `jwt_secret: str = Field(default="dev-secret-change-in-production", validation_alias="JWT_SECRET")`
- `backend/app/core/security.py:54,70` — uso como clave de firma HS256 de access y refresh tokens
- `backend/.env.example` — no lista `JWT_SECRET`
- Contraste: `backend/app/main.py:51` sí es *fail-safe* con la API key (`docs_enabled = not settings.backend_api_key`)

**Qué pasa**

El secreto de firma HS256 tiene un valor por defecto que es un literal público y versionado en git. `pydantic-settings` lo acepta sin complaint: si el deploy no define `JWT_SECRET`, el backend arranca **igual** y firma tokens con una clave que cualquiera que haya leído el repo puede reproducir. No hay validación en startup que aborte, ni warning, ni nada que lo delate.

El patrón ya existe en el mismo codebase y está aplicado a la otra credencial: `main.py:51` deriva `docs_enabled` de la ausencia de `backend_api_key`. Alguien ya pensó el problema para la API key y no lo replicó para el JWT.

El agravante es que `.env.example` no menciona `JWT_SECRET`. Un operador que sigue el ejemplo al pie de la letra produce un deploy con la clave pública.

**Por qué importa**

Quien conozca el default puede firmar un access token válido con el `sub` que quiera — el `sub` es el id de usuario, y con eso se es cualquier cuenta, incluido el service role. Como los access tokens tienen TTL de 15 minutos (`config.py:54`) y el refresh de 30 días (`config.py:55`), un token firmado con el default no solo da 15 minutos: da una sesión renewable. El impacto es *lectura y escritura sobre el CV, el perfil y los datos de facturación de cualquier usuario registrado*, no sólo lectura.

**Estrategia de fix**

1. Rechazar el arranque cuando el secreto es el default y el entorno no es explícitamente de desarrollo. La decisión de diseño a tomar es **cómo se declara "prod"**: opción A, un `ENVIRONMENT`/`APP_ENV` explícito; opción B, fail-closed por defecto (si `JWT_SECRET` no viene del entorno, se aborta siempre y el dev local lo define en su `.env`).
2. Agregar `JWT_SECRET` a `backend/.env.example` con un valor de ejemplo claramente marcado como no-usable, y documentarlo en `docs/DEPLOY.md` (hoy la tabla de env vars no lo incluye).
3. Evaluar migrar de HS256 a asimétrico (RS256/EdDSA). Con HS256 el backend necesita el secreto para *firmar y para verificar*, así que el mismo valor da poder de emisión y de validación. La asimetría separa ambos poderes y permite rotación de claves sin downtime. Tradeoff: más complejidad de configuración, y los refresh tokens heredan el mismo tratamiento.

**Verificación**

Test de settings que instancia la configuración con entorno `production` y `JWT_SECRET` ausente (o igual al default) y asserta que el arranque falla. Complemento: un test que firme un token con el secreto por defecto y asserta que `decode_access_token` lo rechaza tras el fix.

---

## S2 — Modo abierto devuelve un service super-principal sin verificar credencial

> 🟡 **MITIGADO EN PRODUCCIÓN por configuración.** El backend desplegado tiene `BACKEND_API_KEY` seteada (verificado: `/docs` → 404, `/v1/ping` → 401), así que el modo abierto no está activo hoy. Sigue siendo un **bug de diseño y riesgo de deploy futuro** (si alguien quita la key, la superficie se abre sin aviso), pero no es urgencia operativa inmediata. El fix pasa de P0 a P1 en prioridad, después de S1 y S3.

**Severidad:** P0 diseño / P1 operativo (mitigado en prod)

**Ubicación**
- `backend/app/api/deps.py:168-174` — `if not is_auth_required(): return CurrentUser(id=0, name="service", role="service", auth_method="api_key")`
- `backend/app/api/deps.py:36-43` — `is_auth_required()` devuelve `bool(settings.backend_api_key)`
- `mcp-adapter/src/asistcv_mcp/config.py:18` — `backend_api_key` default `None`
- Impacto del `id=0`: `backend/app/api/v1/match.py:90`, `backend/app/api/v1/adaptations.py:226`

**Qué pasa**

Cuando no hay `BACKEND_API_KEY` configurada, `get_current_user` no devuelve "sin auth": devuelve un principal **real** con `role="service"` e `id=0`, sintetizado sin haber verificado ninguna credencial.

Eso es peor que "sin autenticación", por dos razones concretas:

1. **Bypassa RLS.** Las políticas de Postgres están escritas alrededor de `current_setting('app.current_user_id') = '0'` (migraciones `011`, `016`): el id `0` es el wildcard de los policies `*_service_all`. Un `id=0` sintético atraviesa exactamente las mismas políticas que un backend legítimo.
2. **Bypassa los tier limits.** Las comprobaciones de cuota compara `current_user.id` contra el contador del usuario. Con `id=0` la comparación no matchea y `can_use_adaptation()` devuelve `True` siempre: los planes pagos quedan ilimitados.

Mientras tanto, el adapter MCP envía `backend_api_key=None` por defecto (`mcp-adapter/.../config.py:18`). **Nada acopla las dos configuraciones**: es perfectamente posible tener el backend en modo protegido y el adapter MCP desconectado, o el backend abierto y el adapter con key, y ninguno de los dos lados avisa del desalineamiento.

**Por qué importa**

Es un fail-open silencioso por diseño. Un despliegue en producción donde alguien olvida `BACKEND_API_KEY` no falla: arranca, responde, y entrega el service role a cualquier request anónimo. El servicio *parece* sano porque los endpoints responden 200. Y aunque el servicio no quedara abierto, el modo abierto por sí mismo es una superficie de auth por diseño, no una decisión de configuración documentada.

**Estrategia de fix**

1. **Fail-closed en producción:** abortar el arranque si `BACKEND_API_KEY` no está definida y el entorno no es de desarrollo. Sin esto, el resto de los guards son decorativos.
2. **Modo abierto explícito:** que open-mode requiera un opt-in explícito (p.ej. `AUTH_MODE=open` más un flag de entorno de desarrollo), y que en ese caso se loguee un warning de startup **ruidoso y recurrente** — no un `logger.info` de una línea que nadie lee.
3. **Nunca `id=0` para anónimo.** Si el modo abierto tiene que permitir llamadas sin credencial, que devuelva `CurrentUser(id=0, role="anonymous")` y que ninguna política RLS ni comprobación de cuota trate `role="anonymous"` como privileged. La decisión de diseño a tomar es si el funnel anónimo de audit necesita de verdad acceso a datos persistidos, o puede vivir en un camino de código separado sin principal.
4. Añadir un test de configuración que cubra la matriz {prod, dev} × {key presente, key ausente}.

**Verificación**

Test de arranque que instancia la app con entorno de producción y `BACKEND_API_KEY` ausente y asserta que falla. Test de integración que, en modo abierto, confirma que un request anónimo NO obtiene datos de otro usuario y NO puede consumir cuota de un plan pago.

---

## S3 — IDOR en claim de audit (escribe cross-user, sin auth)

> 🔴 **SIGUE EXPLOTABLE EN PRODUCCIÓN.** El funnel anónimo es público por diseño, así que opera con normalidad aunque `BACKEND_API_KEY` esté seteada. `claim_audit` no valida al caller en ningún momento. Que la API key esté seteada **no** protege este endpoint.

**Severidad:** P0

**Ubicación**
- `backend/app/api/v1/audit.py:327-396` — `async def claim_audit(token: str, body: ClaimAuditRequest)`
- `backend/app/api/v1/audit.py:355` — `set_rls_service(...)` antes de escribir
- `backend/app/api/v1/audit.py:357` — única validación: el usuario existe
- Contraste: el resto de `audit.py` sí usa `Depends(get_current_user)`

**Qué pasa**

`claim_audit` es el endpoint que enlaza una auditoría anónima con una cuenta. No tiene `Depends(get_current_user)`: **no hay autenticación en absoluto**. Toma el `user_id` del body de la request, comprueba únicamente que ese usuario exista en la tabla, levanta contexto RLS de service (`set_rls_service`, `:355`) y escribe bajo ese id materializando un `Analysis` completo en la cuenta indicada.

El resultado es un IDOR de escritura: cualquiera que posea un token de auditoría válido — que es lo que recibe cualquier visitante que hace el funnel público — puede reclamar esa auditoría para **cualquier** `user_id` existente. Y al ejecutarse bajo contexto de service, escribe saltándose las políticas RLS que protegerían esa fila.

**Por qué importa**

rompe la frontera entre el funnel anónimo y las cuentas reales en ambas direcciones: el atacante planta un `Analysis` en la cuenta de una víctima, y la víctima ve un análisis que no hizo. Como el análisis se materializa como fila propia y el resto de la app cuenta con RLS para aislar, el dato queda **persistido y visible** para la víctima hasta que se limpie.

Además, el camino inverso importa por la misma ruta: la validación de existencia (`:357`) convierte el endpoint en un **oráculo de enumeración de usuarios** — se puede distinguir "existe" de "no existe" para cualquier id, sin credencial.

**Estrategia de fix**

1. Añadir `current_user: CurrentUser = Depends(get_current_user)` al endpoint.
2. Usar `current_user.id` y **ignorar / rechazar** cualquier `user_id` del body. La decisión de diseño a tomar es si se conserva el campo por compatibilidad (en ese caso, si no coincide, `403` explícito) o se elimina del schema — la opción limpia es eliminarlo.
3. Nunca usar `set_rls_service` desde un endpoint alcanzable por un caller noprivilegiado. Si el claim necesita escribir en la fila del propio usuario, el contexto RLS correcto es el del usuario, no el de service.
4. Revisar si existe algún otro endpoint que tome un id de usuario por body y escriba bajo contexto de service.

**Verificación**

Test que llama a `claim_audit` sin credencial y asserta `401/403`. Test que la llama autenticado como usuario A con `body.user_id = B` y asserta que se rechaza o se ignora el body y el análisis queda bajo A. Test que confirma que el `user_id` inexistente ya no es distinguishable del no-autenticado (fin del oráculo de enumeración).

---

## S4 — Router de audit montado dos veces + kill-switch incompleto

**Severidad:** P0

**Ubicación**
- `backend/app/main.py:186-194` — `audit.router` incluido con prefix `/v1` **y** de nuevo con prefix `""`
- `backend/app/api/v1/adaptations.py:180-183` — `require_adaptation_enabled` solo en `POST /adaptations`
- `backend/app/api/v1/adaptations.py:311`, `:343` — los dos GETs sin el kill-switch
- `backend/app/api/v1/adaptations.py:271` — `jd_text` guardado crudo en una columna llamada `jd_text_encrypted`
- `backend/app/api/v1/adaptations.py:301-308` — `except` que traga el `IntegrityError`

**Qué pasa**

Tres problemas en un mismo módulo, que se refuerzan entre sí.

**Montaje duplicado.** `main.py:186-194` incluye el router de audit dos veces: una con prefix `/v1` y otra con prefix `""`. El funnel público completo queda expuesto en **dos** árboles de rutas, y lo mismo pasa con `/internal/audit/cleanup`, que queda montado también en la raíz pese a estar protegido por token. Duplicar la superficie no es solo.feedback: duplica los puntos de entrada que hay que proteger, auditar y rate-limitar.

**Kill-switch a medias.** `require_adaptation_enabled` está aplicado **solo** al `POST`. Los dos GETs (`:311`, `:343`) no lo llevan. El switch queda a medio camino: se puede apagar la creación y seguir leyendo datos de adaptaciones ya generadas, precisamente lo que un kill-switch de emergencia debería permitir cortar.

**Cifrado que no existe.** `adaptations.py:271` escribe `jd_text` en la columna `jd_text_encrypted` como UTF-8 crudo. El comentario del código lo admite ("wiring is a follow-up"). El nombre de la columna afirma una protección de privacidad que no está implementada — el peor tipo de deuda, porque un revisor que lea el schema asumirá que está cifrado.

**Por qué importa**

Cada uno por separado es un problema; juntos, el conjunto es la razón por la que un incidente en adaptaciones sería difícil de contener. El funnel duplicado multiplica los puntos de entrada del audit anónimo (que es donde vive el rate limit, y ver A-severity: el rate limit es check-then-insert y además se bypasea con `X-Forwarded-For`). El kill-switch parcial impide una mitigación de emergencia. Y el nombre `_encrypted` sobre datos en claro hace que un futuro escaneo de compliance pase el finding por alto.

**Estrategia de fix**

1. **Montar el cleanup en un router interno separado**, con su propio prefix, y eliminar el segundo `include` del router de audit. La decisión de diseño a tomar: si ese router interno debe además quedar fuera del OpenAPI público (recomendado) y si el token de cleanup debería ser rotado tras el despliegue por haber estado duplicado.
2. **Extender `require_adaptation_enabled` a los dos GETs.** Añadir `ADAPTATION_ENABLED` a `backend/.env.example` (hoy no está) para que el switch sea descubrible.
3. **O cifrar o renombrar.** Si el cifrado es el plan (la columna ya se llama así), implementarlo con una clave de aplicación; si no es el plan, renombrar la columna a `jd_text` y registrar la deuda. Renombrar es más barato y honesto; decidir explícitamente y no dejar el nombre mintiendo.
4. Revisar que el `except` de `:301-308` no deje la fila colgada (ver F3, mismo `IntegrityError` en el mismo flujo).

**Verificación**

Test que itere la tabla de rutas de la app y asserta que cada endpoint del audit aparece en **exactamente un** path (detecta el duplicado automáticamente). Test que con `ADAPTATION_ENABLED=false` los GETs de adaptaciones devuelven el mismo `FEATURE_DISABLED` que el POST. Test que asserta que ningún nombre de columna afirma cifrado sin implementación (o, en su defecto, que el round-trip de `jd_text` está cifrado en reposo).

---

# Fase 1 — Bugs funcionales que rompen features (P0/P1)

## F1 — Billing checkout/portal 500: lee atributos que `CurrentUser` no tiene

**Severidad:** P0

**Ubicación**
- `backend/app/api/v1/billing.py:147`, `:201`, `:240` — anotación `current_user: User = Depends(get_current_user)`
- `backend/app/api/deps.py:46-52` — `CurrentUser` es un dataclass con campos `id`, `name`, `role`, `auth_method`
- `backend/app/api/v1/billing.py:158` — lee `current_user.email_verified_at`
- `backend/app/api/v1/billing.py:190` — lee `current_user.email`
- `backend/tests/test_billing.py:152-153` — los tests esquivan el bug sobreescribiendo la dep con la fila ORM
- `backend/app/api/v1/auth.py:359-368` — `POST /v1/auth/verify-email/confirm` es un stub
- `email_verified_at` no se escribe en ningún punto de `app/`

**Qué pasa**

Tres handlers de billing anotan `current_user: User = Depends(get_current_user)` — parkean que el objeto es una fila ORM `User`. Pero `get_current_user` devuelve el dataclass `CurrentUser` (`deps.py:46-52`), que tiene cuatro campos: `id`, `name`, `role`, `auth_method`. **No tiene `email` ni `email_verified_at`.**

Los handlers leen ambas cosas: `current_user.email_verified_at` en el checkout (`:158`) y `current_user.email` al crear el customer de Stripe (`:190`). Los dos son `AttributeError`. Y el `except` de esos handlers captura `ValueError` — no `AttributeError` — así que la excepción sube y sale un 500.

La suite de tests pasa porque el fixture **overridea la dependencia** con la fila ORM completa (`tests/test_billing.py:152-153`). El test ejercita un objeto que la dependencia real nunca produce. Esto es exactamente el patrón que T1 describe: la suite verde no es evidencia cuando el fixture no es la realidad.

Y se agrega una segunda falla, independiente: **`email_verified_at` no se escribe nunca en `app/`**, y `POST /v1/auth/verify-email/confirm` (`auth.py:359-368`) es un stub que devuelve 200 sin verificar nada. El gate de `:158` es insatisfacible: ningún usuario puede estar "verificado", y aunque lo estuviera, no se puede comprar nada.

**Por qué importa**

**Nadie puede comprar un plan.** No es un caso borde: es el revenue path completo. El producto tiene billing, pricing, portal de cliente y webhooks, y el camino de checkout lanza 500 en el primer acceso. Todo el trabajo de Stripe (`stripe_client.py`, webhooks, `STRIPE_PRICE_*`) está construido sobre un endpoint que no se puede ejecutar.

La segunda mitad es peor en diseño: un gate de "email verificado" que retorna 200 sin verificar es peor que no tener gate. Da la impresión de que la verificación existe, y en realidad acepta cualquier token. Cualquiera que confíe en ese endpoint para un control de seguridad está confiando en nada.

**Estrategia de fix**

1. **Decidir la forma del principal.** Dos caminos, y la elección es del fixer:
   - (a) Enriquecer `CurrentUser` con `email` y `email_verified_at` (los obtiene del refresh del user row en `_try_jwt` / `_api_key_auth`). Es la opción que mantiene una sola dependencia y hace que el resto de handlers sean correctos por tipo.
   - (b) Dejar `CurrentUser` mínimo y que los handlers que necesiten email re-consulten el user por `current_user.id`. Menos superficie en el principal, más queries.
   - Recomendación: (a), porque el error de fondo es que el handler asumía un tipo que la dependencia no produce — y eso volverá a pasar en el siguiente handler si no se arregla la firma.
2. **Implementar la verificación de email de verdad**: token con expiración y un solo uso, envío del email, y `confirm` que valide el token, escriba `email_verified_at` y responda distinto a token inválido. Decisión de diseño: qué proveedor de email (Groq no sirve; hace falta algo transaccional) y si se exige verificación antes o después del primer login.
3. **Quitar el override ciego del fixture.** El fixture de billing debe usar la dependencia real o un `CurrentUser` explícitamente enriquecido, para que la suite deje de tapar este bug. Mientras el override exista, cualquier `AttributeError` futuro queda invisible.
4. Revisar el `except ValueError` de esos handlers: capturar `AttributeError` habría convertido un 500 en un error controlado — pero es un parche, no un fix. Sirve como defensa secundaria.

**Verificación**

Test de integración que compra un plan end-to-end: usuario verificado → `POST /v1/billing/checkout` devuelve una sesión de Stripe (no 500). Test que un usuario **no** verificado recibe `403` con el error correcto. Test que `POST /v1/auth/verify-email/confirm` con token inválido o reutilizado no marca el email como verificado.

---

## F2 — El audit "CV vs JD" nunca manda el CV al LLM

**Severidad:** P0

**Ubicación**
- `backend/app/services/audit_runner.py:87-111`
- `backend/app/services/audit_runner.py:106-109` — fallback en `except` que habría usado `cv_text`
- `backend/app/services/audit_runner.py:46-51` — docstring de `run_audit`; parámetros `session` y `pdf_bytes` sin uso
- `backend/app/core/config.py:43-45` — `retrieval_size_threshold_chars = 3000`

**Qué pasa**

En el camino `jd_directed` del funnel de auditoría, `audit_runner.py:87-111` construye un `Profile` **vacío** de mock (`Profile(id=0, ...)`) y llama a `retrieve_profile_context` sobre él.

El retrieval decide el modo por tamaño del perfil. Con el perfil vacío, el texto queda muy por debajo del umbral de 3000 caracteres (`config.py:43-45`), así que **no es un fragmento**: retorna `mode="complete"` con contexto vacío **sin lanzar excepción**. Y ese es el punto exacto del bug — el `except` de `:106-109`, que era el camino que iba a usar el `cv_text` real, nunca se ejecuta, porque no hay nada que capturar.

Consecuencia: el CV subido **se almacena en la base pero nunca influye en el score**. El análisis es JD contra un perfil vacío. El usuario sube su CV, espera un match contra su CV, y recibe un análisis contra la nada.

De paso, `run_audit` recibe `session` y `pdf_bytes` que no usa (`:46-51`), y el docstring de `pdf_parser.py:3-5` promete streaming de 64KB mientras el archivo entero se lee en memoria. Los parámetros muertos son la huella de que el wiring quedó a medio camino.

**Por qué importa**

Es la **primera** interacción del funnel público — el producto se acquisition vía el audit anónimo. Si el audit anónimo devuelve un score que no tiene en cuenta el CV, entonces el score no significa nada, y la promesa de "score honesto de match" del `PROJECT.md:28` es falsa justo en el punto de mayor visibilidad. Un usuario que pegue un CV bueno y un JD razonable obtiene un score que no refleja ninguno de los dos.

Peor aún: devuelve un resultado **con apariencia de válido**. No es un error, es un score. El usuario no tiene forma de saber que su CV fue ignorado.

**Estrategia de fix**

1. En el camino `jd_directed`, construir el contexto desde el `cv_text` real (el texto parseado del PDF) en lugar de un `Profile` vacío. La decisión de diseño a tomar: si la adaptación necesita el CV parseado a `Profile` completo, parsearlo de verdad, o extender el prompt de match para que acepte texto de CV libre como segundo input. La segunda es más simple y evita depender de la extracción por regex que ya se sabe lossy (ver L1(e)).
2. **Revisar el contrato del retrieval.** El umbral de 3000 caracteres convierte "perfil vacío" en un *short-circuit de éxito* en lugar de un error. Para un `jd_directed`, un perfil sin contenido debería ser un error explícito o forzar el camino de fallback, no un `mode="complete"` con contexto vacío. Sin este cambio, el fix de (1) es frágil: cualquier refactor que vuelva a dejar el perfil vacío reintroduce el bug en silencio.
3. Eliminar los parámetros muertos `session` / `pdf_bytes` o implementarlos. Un parámetro sin uso y un docstring que promete streaming que no existe son dos mentiras documentadas en el punto exacto donde falla la feature.
4. Corregir la docstring de `pdf_parser.py` para que describa el comportamiento real, o implementar el streaming.

**Verificación**

Test que corre un audit con un CV que contiene una frase marcadamente distintiva (p.ej. un número o skill que no aparece en el JD) y asserta que esa frase influence el score o el razonamiento devuelto. Test de regresión sobre el perfil vacío: un audit sin CV debe fallar explícitamente o pedir el CV, no devolver un score de 0 silencioso.

---

## F3 — La cuota de adaptaciones nunca se consume (RLS GUC no bindeado en el runner)

**Severidad:** P1

**Ubicación**
- `backend/app/services/adaptation_runner.py:355-370` — `_increment_usage` abre sesión nueva y llama `increment_usage` sin ningún `set_rls_*`
- `backend/app/services/adaptation_runner.py:365-370` — excepción tragada como `adaptation_usage_increment_failed`
- `backend/app/services/adaptation_runner.py:318` — `IntegrityError` tragado
- `backend/app/api/v1/adaptations.py:301-308` — `except` que traga el `IntegrityError`
- `backend/migrations/versions/015_*.py:111-121` — índice único parcial `uq_cv_adapt_parent_jd_hash_completed`
- `backend/app/db/session.py:55` — `NullPool`

**Qué pasa**

`_increment_usage` abre una **sesión nueva** y llama a `increment_usage` sin emitir ningún `set_rls_user(...)` ni `set_rls_service(...)`. Tres consecuencias encadenadas:

1. `usage_counters` tiene **RLS forzado** y solo tiene una policy de service (`current_setting('app.current_user_id') = '0'`) más policies de owner basadas en `app_current_user_id()`. Sin GUC bindeada, el GUC no está seteado.
2. El engine usa `NullPool` sin `server_settings` (`session.py:55`), así que no hay configuración de servidor que compense. El `SELECT` de lectura devuelve **0 filas**, y el `INSERT` falla el `WITH CHECK` (la expresión evalúa NULL, no true).
3. La excepción se **traga** en `adaptation_runner.py:365-370` y se loguea como `adaptation_usage_increment_failed`. El request responde 200.

Resultado: `can_use_adaptation()` siempre lee `adaptations_used=0`. **Los planes pagos quedan ilimitados** — el producto cobra por un límite que nunca se aplica. Y como la excepción está tragada, no hay señal: los logs tienen una línea, el dashboard no.

El problema adyacente (mismo `IntegrityError`, mismo flujo): el índice único parcial `uq_cv_adapt_parent_jd_hash_completed` (`015:111-121`) cubre solo las adaptaciones **completadas**. Combinado con el TTL de cache de 24h y el sweeper de 90 días, una repetición de la misma adaptación entre 24h y 90 días inserta una fila nueva (el índice no la cubre todavía) cuyo `UPDATE` de completado viola el índice único → la fila queda **atascada en `pending` para siempre**, porque el `IntegrityError` en `adaptation_runner.py:318` se traga y `adaptations.py:301-308` lo silencia.

**Por qué importa**

Es un hallazgo de integridad **y** de negocio a la vez. El revenue model del producto es por tiers con límites; un límite que nunca se incrementa no es un bug de contabilidad, es un bug de modelo de negocio. Y el `except` que traga la excepción es lo que convierte un error ruidoso en un silencio: sin él, el primer usuario de un plan pago habría reportado "no me cobra el límite".

La fila en `pending` eterno es el segundoSymptoms: el usuario pide una adaptación, la UI queda en polling, y no hay error — solo nunca termina.

**Estrategia de fix**

1. **Bindear el contexto RLS en `_increment_usage`** antes de llamar a `increment_usage`, exactamente igual que se hace en los demás puntos del codebase. Además: reutilizar la sesión del request en lugar de abrir una nueva, que además elimina una clase entera de problemas de RLS.
2. **Dejar de tragar la excepción en silencio.** El `except` de `:365-370` debería loguear con nivel `error` y suficiente contexto, o propagar. La decisión de diseño a tomar: si el contador es crítico para el cobro, la respuesta debe fallar (fail-closed) en lugar de servir la adaptación gratis.
3. **Reconciliar las tres cosas que colisionan:** el índice único parcial (`015:111-121`), el TTL de cache de 24h, y el sweeper de 90 días. La opción más simple es ampliar la condición del índice para cubrir la ventana relevante, o hacer el upsert idempotente. Lo que no puede seguir es un esquema donde la operación legítima falla y el error se come.
4. **Revisar todos los demás `except` que tragan `IntegrityError`** en el flujo de adaptaciones. Un `except` de amplio que convierte un error de integridad en un no-op es un patrón, no un incidente aislado.

**Verificación**

Test que corre N adaptaciones y asserta que `adaptations_used` es exactamente N. Test de tier: un plan pago con límite de 5 falla en la sexta adaptación con el error esperado. Test de repetición: la misma adaptación (mismo `jd_hash`) re-ejecutada ~25h después **completa** y no queda en `pending`. Test de concurrencia: dos adaptaciones simultáneas del mismo padre producen exactamente una fila completada.

---

# Fase 2 — Honestidad del LLM + deuda de tests/CI (P1)

## L1 — "Nunca inventa experiencia" se cumple solo léxicamente; los números nunca se verifican

**Severidad:** P1

**Ubicación**
- `backend/app/services/adaptation_validator.py` — el validador completo
- `backend/app/services/adaptation_validator.py:40` — `_MIN_TOKEN_LEN = 3`
- `backend/app/services/adaptation_validator.py:185-187` — filtro de tokens
- `backend/app/services/adaptation_validator.py:143-156` — `_is_substring_of` bidireccional
- `backend/app/services/adaptation_validator.py:121-135` — construcción de `source_blob`
- `backend/app/services/adaptation_validator.py:222-231` — validación de la fuente
- `PROJECT.md:32` — la promesa: *"jamás inventa skills o logros"*
- `PROJECT.md:43` — el anti-patrón declarado: *"No inventa experiencia"*
- `backend/app/services/pdf_parser.py:260-320` — extracción por regex de PDFs
- `backend/app/services/adaptation_validator.py:121` — fuente de verdad: `users_cvs.structured`

**Qué pasa**

El enforcement de la promesa central del producto **existe y es real** — hay un validador dedicado. El problema es que su alcance es mucho más estrecho de lo que parece cuando se lee el nombre de la función.

**(a) Los números nunca se verifican.** `_MIN_TOKEN_LEN = 3` (`:40`) combinado con el filtro de tokens (`:185-187`) descarta todo token de menos de 3 caracteres. Una afirmación numérica inventada es — por definición — corta: `40%`, `30%`, `2x`, `10k`, `5M`. **Ninguna se verifica jamás.** Y una métrica fabricada es exactamente el "logro inventado" que el producto dice no hacer. Un LLM que añade "aumenté los ingresos 40%" a un bullet pasa el validador sin una sola objeción.

**(b) El match de skills es bidireccional.** `_is_substring_of` (`:143-156`) es `needle in hay or hay in needle`. Al ser bidireccional, una skill fuente corta whitelisteara cualquier skill más larga que la contenga: una skill fuente de `"R"` valida `"React"`. Lo mismo en la dirección inversa, lo que además produce ruido en el sentido opuesto.

**(c) `full_name`, `education` y `languages` nunca se inspeccionan.** El validador no mira esos campos, así que son de facto zonas sin restricción: el modelo puede alterarlos libremente.

**(d) No hay check de "difiere del original" ni de "está anclado al JD".** Una copia exacta del CV fuente pasa todas las validaciones. El validador no puede distinguir "adaptación" de "copia", lo que significa que una adaptación que no adapta nada se considera válida.

**(e) `source_blob` concatena todas las descripciones de experiencia** (`:121-135`). No hay identidad de qué experiencia produce qué bullet en la salida. Una frase del puesto 3 puede moverse al puesto 1 del CV adaptado y no viola nada, porque el validador solo pregunta "¿esta frase existe en el CV?".

**(f) La fuente de verdad es `users_cvs.structured`**, que para PDFs viene de una extracción por regex (`pdf_parser.py:260-320`) — inherentemente lossy. El `raw_text` real no se usa. Para PDFs, el validador está verificando contra una reconstrucción incompleta del CV, lo que a la vez genera falsos positivos (rechaza algo que sí estaba en el CV original) y deja huecos.

**Por qué importa**

Es el riesgo de **reputación** más alto del producto, y no aparece en ninguna métrica. `PROJECT.md:32` y `:43`.Repiten la promesa dos veces, en la solución y en los anti-patrones: es la razón por la que un reclutador confía en la salida. Un único bullet con "reduje el tiempo de carga 40%"_when_ el CV dice otra cosa destruye esa confianza de forma permanente, y el usuario no tiene forma de detectarlo: el validador no se lo va a decir.

El patrón (a) es el más grave porque el failure mode del LLM en un CV Bullets es *precisamente* la métrica roja, y es la que más plausible resulta. Los modelos están entrenados para cuantificar logros. La regla que filtra los tokens cortos es, irónicamente, la que garantiza que sus cuantificaciones nunca se revisen.

**Estrategia de fix**

1. **Verificar tokens numéricos y de métrica contra la fuente**, en vez de saltárselos. La regla a cambiar: no descartar tokens cortos por shortness, sino verificar los que son numéricos/porcentuales/multiplicadores aunque sean de 1-2 caracteres. **Decisión de diseño explícita que el fixer debe tomar:** cuán estricto ser con el matching numérico sin generar falsos positivos. `"40%"` en la fuente y `"40 %"` en la salida, o `"+40%"` vs `"40%"`, o un número redondeado — si el matching es literal, el validador va a rechazar adaptaciones legítimas y los usuarios van a reportar "el sistema me rechaza CVs válidos". Un enfoque razonable: extraer la forma normalizada de la métrica (valor + unidad) y comparar con tolerancia explícita, en vez de comparación de strings.
2. **Hacer el match de skills unidireccional o basado en conjunto de tokens.** La comparación bidireccional (`:143-156`) no expresa la relación que se quiere. Un set de tokens normalizado (lowercase, split por separadores) elimina la clase de bug del `"R"` → `"React"`.
3. **Validar los campos hoy no inspeccionados** (`full_name`, `education`, `languages`) con la misma regla que el resto.
4. **Añadir un check de diferencia mínima respecto del original**, y opcionalmente un check de anclaje al JD. Sin esto, "adaptar" y "copiar" son indistinguibles para el sistema.
5. **Dar identidad a las experiencias**: en lugar de un `source_blob` plano (`:121-135`), validar los bullets de salida contra las experiencias que la salida dice usar. Esto es más invasivo (cambia el schema de la salida) pero cierra el hole de reasignación.
6. **Decidir la fuente de verdad para PDFs.** Si `raw_text` es más completo que `structured`, validar contra `raw_text` y usar `structured` solo para estructura. Considerar que la extracción por regex es un preprocesamiento, no la fuente de verdad.

**Verificación**

Test negativo: una adaptación que introduce "40% revenue growth" cuando el CV fuente no lo contiene debe ser **RECHAZADA** con el error correspondiente. Test positivo: una adaptación que reutiliza métricas realmente presentes en la fuente debe **pasar**. Test de la skill corta: una fuente con skill `"R"` no debe whitelistear `"React"`. Test de reasignación: mover una frase de la experiencia 3 a la experiencia 1 debe fallar.

---

## T1 — CI nunca corre los tests de frontend; el path crítico de RLS/auth nunca se ejercita; sin `permissions:`

**Severidad:** P1

**Ubicación**
- `frontend/package.json:13` — script `vitest run` definido
- Siete archivos de test de frontend, ~46 tests
- `.github/workflows/ci.yml:141-166` — único job de frontend: `npm ci` + paridad de i18n + un grep
- `backend/tests/conftest.py:48-62` — hook global `after_begin` que reaplica contexto RLS de SERVICE en **toda** transacción
- `backend/tests/test_rls.py:61` — confirma que las aserciones de RLS pasan por el bypass del DI

**Qué pasa**

Tres huecos que se refuerzan.

**(a) El frontend tiene tests y CI no los corre.** `frontend/package.json:13` define `vitest run` y existen 7 archivos (~46 tests). Pero el único job de frontend en CI (`.github/workflows/ci.yml:141-166`) ejecuta `npm ci`, un check de paridad de i18n y un grep. Ni `npm run test` ni `npm run check` los invoca **ningún** workflow. Los tests existen y son inertes: no pueden detectar una regresión porque nadie los ejecuta.

**(b) Todos los tests de endpoint corren bajo el bypass de RLS.** `conftest.py:48-62` instala un hook `after_begin` global que **re-aplica el contexto RLS de SERVICE en cada transacción**. El efecto es que cada test de endpoint se ejecuta bajo el bypass de RLS, no bajo el contexto per-user. `test_rls.py:61` lo confirma explícitamente.

La consecuencia es grave yEasy de subestimar: el path per-user de RLS en `get_db` **nunca se ejercita a través de FastAPI**. La línea que bindea la GUC del usuario — la que realmente aísla los datos en producción — no tiene cobertura. El día que esa línea se rompa, la suite seguirá verde. Y es exactamente la línea que S2 vuelve relevante.

El efecto secundario es que los tests no pueden detectar nunca el problema de F3 (GUC sin bindear en `_increment_usage`): el hook global lo tapa.

**(c) Ningún workflow declara `permissions:`.** Todos los jobs heredan el scope por defecto del `GITHUB_TOKEN`. Con el scope por defecto, el token de CI puede escribir en el repo, y los third-party actions corren con esos permisos.

**Por qué importa**

Fase 2 es la fase de "que no se pudra". Con (a) y (b), cualquier fix que hagamos en las fases 0 y 1 puede revertirse sin que nada lo note. El gap de RLS no es teórico: es la misma clase de bug que S2 y F3, y está en el mecanismo que debería detectarla.

F1 es el ejemplo perfecto de por qué: el fixture de billing sobreescribe la dependencia real (`tests/test_billing.py:152-153`) y el resultado es un 500 en producción con la suite en verde. Cuando el harness difiere de la realidad, la suite verde no es información.

**Estrategia de fix**

1. **Agregar `npm run test` y `npm run check` al job de frontend** en `.github/workflows/ci.yml`. Con 46 tests, el costo marginal es bajo; el no correrlos es el que no tiene defensa.
2. **Añadir un test que ejercite el path RLS per-user vía el DI real** — es decir, un test que pase por `get_db` de FastAPI con un token de un usuario y confirme que no ve los datos de otro. El hook global de `conftest.py:48-62` tiene que ser **opt-in** (un fixture que se pide explícitamente) en vez de global, para que exista al menos un test que corra sin él.
3. **`permissions:` con mínimo privilegio en cada workflow**, idealmente `contents: read` por defecto y `permissions` elevados solo en los jobs que los necesitan (release, deploy). La decisión de diseño a tomar: `permissions` a nivel de workflow con overrides por job, o `permissions` por job solamente. El segundo es más explícito y más fácil de auditar.
4. **Clavar las third-party actions por SHA** en lugar de tags mutables. Un tag puede ser re-apuntado; un SHA no.

**Verificación**

Se rompe deliberadamente un test de frontend y se verifica que CI falla. Test de aislamiento RLS per-user que **falla si el hook global de service está activo** — es decir, que el propio test es la prueba de que el hook no se aplica. Idealmente el hook se vuelve opt-in y el conteo de tests que dependen de él queda explícito.

---

# Fase 3 — Docs, stubs y deuda menor (P2)

Los tres hallazgos de esta fase no se detallan aquí: son de mantenimiento, no de riesgo, y su detalle vive en el catálogo. Se resumen para dejar la fase completa y para que el plan no tenga un hueco.

### D1 — Drift documental: los docs describen un producto que no existe

`README.md`, `STACK.md`, `PROJECT.md` y `ROADMAP.md` describen una herramienta personal pre-auth sobre GCP; el código es un SaaS multi-tenant con billing sobre Render. `README.md` dice "Sprint 0 en curso" mientras `ROADMAP.md` dice Sprint 0 cerrado; el badge dice "Apache 2.0" y el cuerpo dice "License: TBD". `README.md` anuncia **Outreach** y **Tracking Pipeline**, y **ninguno de los dos existe** — sin código, sin migraciones, sin rutas. Detalle: `90-catalogo-completo.md` → sección "Docs / deuda".

**Estrategia de fix:** reescribir los cuatro documentos contra el código real, o declarar explícitamente el scope real (Match + Adaptation) y mover Outreach / Tracking a "no implementado". Agregar al final de cada doc una nota de fecha de última verificación contra el código.

### D2 — `Makefile` con stubs que el README documenta como funcionales

`setup`, `test`, `lint` y `deploy` son TODO stubs que salen con código 0 sin hacer nada. El README y `PROJECT.md` los documentan como comandos working. Un `make test` que pasa sin correr tests es peor que un comando inexistente: da confianza falsa. `infra/README.md` tiene el mismo problema, describiendo Cloud Run / Cloud SQL / Artifact Registry / Terraform que no existen.

**Estrategia de fix:** implementar los targets o marcarlos como no disponibles de forma que el error sea visible (salir con código distinto de 0 y un mensaje que apunte a la alternativa real). Nunca dejar un no-op que responda éxito.

### D3 — Código muerto acumulado

`TokenRevocation` (tabla nunca consultada), `Payment` (nunca escrita), el servicio `cv_storage` (solo referencias comentadas), `init_db` / `close_db` (nunca llamados), el bloque `init/close` del lifespan, helpers de consent, `ROLE_IMMUTABLE` (inalcanzable: el schema no tiene campo `role`), `stripe_client.create_customer`, `pdf_parser.CHUNK_SIZE` / `validate_file_size`, y `_debug_safe_headers` en el MCP adapter. Detalle: `90-catalogo-completo.md` → sección "Código muerto".

**Estrategia de fix:** eliminar, o marcar como `@deprecated` con la razón. La tentación de "dejarlo por si acaso" es lo que convierte una capa en difícil de entender en pocos meses.
