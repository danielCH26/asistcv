# Delta para match-ui

## MODIFIED Requirements

### Requirement: Sesión de usuario vía JWT (en lugar de API key de build)

La UI mantiene una sesión de usuario: tras login/registro, guarda
el `access_token` y `refresh_token` en almacenamiento seguro del
cliente (cookie httpOnly si se sirve vía BFF, o `localStorage` con
refresco proactivo si se mantiene estático) y envía
`Authorization: Bearer <jwt>` en cada llamada. La API key de
build-time deja de existir y nunca aparece en el bundle.

(Previously: `PUBLIC_BACKEND_API_KEY` se inyectaba al bundle y
se enviaba como Bearer en cada request.)

#### Scenario: Login persiste tokens

- GIVEN el usuario envía credenciales válidas en
  `POST /v1/auth/login`
- WHEN el backend responde 200 con `access_token` y `refresh_token`
- THEN la UI persiste ambos tokens de forma segura
- AND todas las llamadas subsiguientes envían
  `Authorization: Bearer <access_token>`

#### Scenario: Refresh automático antes de expirar

- GIVEN el `access_token` está a < 60 s de expirar
- WHEN la UI intenta una nueva llamada
- THEN primero llama a `POST /v1/auth/refresh` con el
  `refresh_token`
- AND renueva el `access_token` antes de enviar la llamada de
  negocio

#### Scenario: Refresh falla y fuerza logout

- GIVEN el `refresh_token` está revocado o expirado
- WHEN la UI intenta refrescar
- THEN recibe 401 y limpia los tokens
- AND redirige a `/login`

#### Scenario: Build sin variable de API key

- GIVEN `PUBLIC_BACKEND_API_KEY` ya no se usa
- WHEN se ejecuta el build de producción
- THEN el build no falla por variables de API key ausentes
- Y el bundle no contiene ninguna API key en texto plano

#### Scenario: No hay credenciales hardcodeadas

- GIVEN el código fuente de la UI
- WHEN se hace grep por `BACKEND_API_KEY`, `Bearer ` literal o
  strings sospechosas
- THEN no aparecen valores de credenciales reales

## ADDED Requirements

### Requirement: Formulario de JD

UI con formulario que acepta texto libre de JD y lo envía a
`POST /v1/match` usando el JWT de sesión.

#### Scenario: Envío exitoso autenticado

- GIVEN un JD pegado de ≥ 50 caracteres
- AND el usuario autenticado con sesión JWT activa
- WHEN el usuario envía el formulario
- THEN la UI muestra indicador de carga
- AND al recibir 200 navega a la vista de resultado con `score`,
  `strengths`, `gaps`, `energy_level`, `reasoning`

#### Scenario: Validación cliente de JD corto

- GIVEN el JD pegado tiene menos de 50 caracteres
- WHEN el usuario intenta enviar
- THEN la UI muestra mensaje de validación y bloquea el envío

#### Scenario: Error 401 mostrado con claridad

- GIVEN la sesión JWT es inválida o expiró
- WHEN el backend responde 401
- THEN la UI intenta un refresh silencioso
- Y si el refresh falla, redirige a `/login` con un mensaje
  accionable

#### Scenario: Error de red o 5xx con retry

- GIVEN el backend retorna 5xx o hay error de red
- WHEN la llamada falla
- THEN la UI muestra error con opción de reintentar

#### Scenario: Límite de plan alcanzado

- GIVEN el backend responde 402 con código `PLAN_LIMIT_REACHED`
- WHEN la UI recibe el error
- THEN muestra un CTA al upgrade del plan con link a
  `/billing/plans`

### Requirement: Vista de resultado del match

La vista de resultado renderiza `MatchAnalysis` con `score`
destacado, listas de `strengths`/`gaps`, badge de `energy_level`
y bloque de `reasoning`.

#### Scenario: Render correcto

- GIVEN un `MatchAnalysis` válido
- WHEN el usuario abre la vista de resultado
- THEN `score` se muestra como entero
- AND `strengths`/`gaps` se renderizan como listas
- AND `energy_level` aparece como etiqueta coloreada
  (`low|medium|high`)
- AND `reasoning` aparece como bloque de texto

### Requirement: Historial de análisis

La UI lista análisis previos consumiendo `GET /v1/analyses`,
filtrado por el usuario autenticado.

#### Scenario: Carga del historial autenticado

- GIVEN el usuario autenticado abre la vista de historial
- WHEN el componente se monta
- THEN se llama a `GET /v1/analyses` con el JWT de sesión
- AND se renderiza una lista con score, fecha y referencia al JD

#### Scenario: Historial vacío

- GIVEN el usuario autenticado no tiene análisis previos
- WHEN se carga la vista
- THEN la UI muestra mensaje localizado ("Aún no hay análisis"
  / "No analyses yet")

#### Scenario: Click en un análisis

- GIVEN la lista de historial muestra N análisis
- WHEN el usuario hace clic en uno
- THEN la UI navega a `/analyses/{id}` y carga el detalle vía
  `GET /v1/analyses/{id}`

### Requirement: Internacionalización bilingüe ES/EN

UI en español e inglés, detección del idioma del navegador y
toggle manual. Librería: `svelte-i18n`.

#### Scenario: Idioma por defecto del navegador

- GIVEN el navegador reporta `Accept-Language: es`
- WHEN el usuario abre la app por primera vez
- THEN todos los textos visibles se muestran en español

#### Scenario: Toggle manual persistente

- GIVEN el usuario cambia el toggle de ES a EN
- WHEN recarga la página
- THEN la UI se renderiza en inglés
- AND la preferencia persiste en `localStorage`

#### Scenario: Cobertura i18n completa

- GIVEN los catálogos `es.json` y `en.json` versionados
- WHEN se valida en CI
- THEN todas las claves usadas en componentes tienen entrada en
  ambos idiomas
- AND CI falla si falta alguna clave

### Requirement: Onboarding 3 pasos

Tras el primer registro, la UI guía al usuario nuevo por un
wizard de 3 pasos: (1) selección/confirmación de rol,
(2) completar perfil básico, (3) ejecutar el primer match.

#### Scenario: Paso 1 — rol

- GIVEN un usuario recién registrado con sesión JWT activa
- WHEN entra por primera vez a la app
- THEN la UI muestra el paso 1 con el rol ya seleccionado
- AND permite corregir `locale` y `full_name`

#### Scenario: Paso 2 — perfil

- GIVEN el usuario avanzó al paso 2
- WHEN sube un PDF o completa campos del editor estructurado
- THEN la UI llama a `POST /v1/cvs`
- Y al recibir 201 avanza al paso 3

#### Scenario: Paso 3 — primer match

- GIVEN el usuario tiene un CV propio
- WHEN pega un JD y envía el formulario
- THEN la UI ejecuta `POST /v1/match`
- Y muestra el resultado, marcando el fin del wizard

#### Scenario: Salir del wizard

- GIVEN el usuario en cualquier paso del wizard
- WHEN cierra o navega a otra ruta
- THEN la UI recuerda el último paso visitado
- Y al volver continúa desde ese paso (no reinicia)

### Requirement: Deploy estático en Cloudflare Pages

Frontend con `@sveltejs/adapter-static` para generar artefactos
compatibles con Cloudflare Pages.

#### Scenario: Build genera sitio estático

- GIVEN `adapter-static` configurado en `svelte.config.js`
- WHEN se ejecuta `npm run build`
- THEN se genera `build/` con HTML, JS y assets servibles

#### Scenario: SPA routing sin servidor

- GIVEN el usuario navega a `/analyses/123`
- WHEN Cloudflare Pages sirve el sitio
- THEN la app resuelve la ruta del lado del cliente y muestra
  el detalle
