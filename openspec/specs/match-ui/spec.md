# Spec: match-ui

## ADDED Requirements

### Requirement: Formulario de JD

UI con formulario que acepta texto libre de JD y lo envía a `POST /v1/match`.

#### Scenario: Envío exitoso

- GIVEN un JD pegado de ≥ 50 caracteres
- AND la API key disponible en el bundle de build
- WHEN el usuario envía el formulario
- THEN la UI muestra indicador de carga
- AND al recibir 200 navega a la vista de resultado con `score`, `strengths`, `gaps`, `energy_level`, `reasoning`

#### Scenario: Validación cliente de JD corto

- GIVEN el JD pegado tiene menos de 50 caracteres
- WHEN el usuario intenta enviar
- THEN la UI muestra mensaje de validación y bloquea el envío

#### Scenario: Error 401 mostrado con claridad

- GIVEN la API key enviada no es válida
- WHEN el backend responde 401
- THEN la UI muestra mensaje accionable sobre credenciales

#### Scenario: Error de red o 5xx con retry

- GIVEN el backend retorna 5xx o hay error de red
- WHEN la llamada falla
- THEN la UI muestra error con opción de reintentar

### Requirement: Vista de resultado del match

La vista de resultado renderiza `MatchAnalysis` con `score` destacado, listas de `strengths`/`gaps`, badge de `energy_level` y bloque de `reasoning`.

#### Scenario: Render correcto

- GIVEN un `MatchAnalysis` válido
- WHEN el usuario abre la vista de resultado
- THEN `score` se muestra como entero
- AND `strengths`/`gaps` se renderizan como listas
- AND `energy_level` aparece como etiqueta coloreada (`low|medium|high`)
- AND `reasoning` aparece como bloque de texto

### Requirement: Historial de análisis

La UI lista análisis previos consumiendo `GET /v1/analyses`.

#### Scenario: Carga del historial

- GIVEN el usuario abre la vista de historial
- WHEN el componente se monta
- THEN se llama a `GET /v1/analyses` con la API key
- AND se renderiza una lista con score, fecha y referencia al JD

#### Scenario: Historial vacío

- GIVEN no hay análisis previos
- WHEN se carga la vista
- THEN la UI muestra mensaje localizado ("Aún no hay análisis" / "No analyses yet")

### Requirement: Internacionalización bilingüe ES/EN

UI en español e inglés, detección del idioma del navegador y toggle manual. Librería: `svelte-i18n` (más simple y mejor documentada para `adapter-static` que paraglide).

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
- THEN todas las claves usadas en componentes tienen entrada en ambos idiomas
- AND CI falla si falta alguna clave

### Requirement: API key vía build-time env

La API key se inyecta desde `PUBLIC_BACKEND_API_KEY` al build. Nunca aparece en código fuente versionado.

#### Scenario: Build falla sin la env var

- GIVEN `PUBLIC_BACKEND_API_KEY` no definida
- WHEN se ejecuta el build de producción
- THEN el build falla con un error explícito

#### Scenario: Key inyectada en runtime

- GIVEN `PUBLIC_BACKEND_API_KEY` definida al build
- WHEN la app carga en el navegador
- AND cualquier llamada al backend envía `Authorization: Bearer <key>`

### Requirement: Deploy estático en Cloudflare Pages

Frontend con `@sveltejs/adapter-static` para generar artefactos compatibles con Cloudflare Pages.

#### Scenario: Build genera sitio estático

- GIVEN `adapter-static` configurado en `svelte.config.js`
- WHEN se ejecuta `npm run build`
- THEN se genera `build/` con HTML, JS y assets servibles

#### Scenario: SPA routing sin servidor

- GIVEN el usuario navega a `/analyses/123`
- WHEN Cloudflare Pages sirve el sitio
- THEN la app resuelve la ruta del lado del cliente y muestra el detalle
