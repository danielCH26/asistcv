# CORS — Notas para el deploy

Este archivo documenta qué necesita el backend para que el frontend (hosteado en
Cloudflare Pages) pueda llamarlo desde el navegador sin errores de CORS. Es
**documentación, no código que se ejecute**: la configuración vive en Render y en
Cloudflare Pages; el cambio manual que sigue está descripto en
[`docs/DEPLOY.md`](../DEPLOY.md).

## Por qué hace falta CORS

El backend (`asistcv-backend.onrender.com`) expone `POST /v1/match` y
`GET /v1/analyses` (más `GET /v1/analyses/{id}`). El frontend estático vive en
otro origen (`asistcv-frontend.pages.dev` o el dominio custom que se configure).
Los navegadores bloquean por defecto las requests cross-origin cuando el backend
no incluye los headers `Access-Control-Allow-*` correctos.

El backend ya implementa CORS con FastAPI middleware y lee la lista de orígenes
permitidos de la env var `CORS_ORIGINS` (CSV). Lo único que hay que configurar
es esa env var con el dominio del frontend.

## Configuración en Render (manual)

1. Render dashboard → `asistcv-backend` → **Environment**.
2. **Add Environment Variable**:
   - **Key**: `CORS_ORIGINS`
   - **Value**: lista CSV con el dominio de Cloudflare Pages. Ejemplos:
     - Dev local + preview Pages: `http://localhost:5173,http://localhost:4173,https://asistcv-frontend.pages.dev`
     - Solo prod: `https://asistcv-frontend.pages.dev`
     - Con dominio custom: `https://asistcv.example.com`
3. **Save Changes** — Render redeploys automáticamente.

> Importante: el valor es **CSV sin espacios alrededor de la coma**. Si agregás
> espacios, el parser los interpreta como parte del origen y falla el match.

## Verificación

Después del redeploy, abrí la consola del navegador en la URL del frontend y
verificá:

```js
fetch('https://asistcv-backend.onrender.com/v1/analyses?limit=1', {
  headers: { Authorization: 'Bearer <PUBLIC_BACKEND_API_KEY>' }
})
  .then((r) => r.json())
  .then(console.log)
  .catch(console.error);
```

- ✅ Array JSON (vacío o con items) → CORS correcto.
- ❌ `TypeError: Failed to fetch` o error de CORS en consola → falta agregar el
  origen a `CORS_ORIGINS`.

También podés revisar los headers de la response con la pestaña **Network** de
DevTools: tiene que estar `access-control-allow-origin: https://<tu-frontend>`.

## Dominios a incluir

| Entorno | Origen |
|---|---|
| Dev local (Vite) | `http://localhost:5173` |
| Preview local (Vite preview) | `http://localhost:4173` |
| Cloudflare Pages (URL auto-generada) | `https://asistcv-frontend.pages.dev` |
| Dominio custom (cuando exista) | `https://asistcv.example.com` |

Mientras el frontend siga en la URL default de Cloudflare Pages, basta con
`https://asistcv-frontend.pages.dev`. Si se suma dominio custom, agregarlo a la
misma env var.

## Rotación futura de dominio

Si Cloudflare Pages regenera el subdominio (raro, pero pasa al recrear el
proyecto) o se migra a dominio custom, actualizar `CORS_ORIGINS` con el nuevo
valor. Es una env var, no requiere cambio de código.

## Referencias

- [`docs/DEPLOY.md`](../DEPLOY.md) — deploy del backend en Render y nota sobre
  CORS al final del archivo.
- [MDN — CORS](https://developer.mozilla.org/en-US/docs/Web/HTTP/CORS) — referencia.