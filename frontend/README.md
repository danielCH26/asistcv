# Frontend

SvelteKit + adapter-static frontend for AsistCV. Single-page application that
hits the FastAPI backend (Render) and renders an honest match between a job
description and the user's profile.

## Stack

- **SvelteKit 2.15** + Svelte 4
- **TypeScript**
- **adapter-static** (SPA fallback, no Node runtime)
- **svelte-i18n** for ES/EN bilingual UI
- **Vite 5** build

## Project structure

```
frontend/
├── src/
│   ├── app.css            # global styles + CSS vars
│   ├── lib/
│   │   ├── api/           # fetch wrapper, types, env guard
│   │   ├── components/    # presentational components
│   │   ├── i18n/          # svelte-i18n setup + locales/{es,en}.json
│   │   └── stores/        # analysis / history / profile writables
│   └── routes/
│       ├── +layout.svelte
│       ├── +page.svelte          # /         JdForm + MatchResult
│       └── history/
│           ├── +page.svelte      # /history  HistoryList (paginated)
│           └── [id]/+page.svelte # /history/{id}  analysis detail
├── scripts/
│   ├── check-env.mjs            # prebuild guard (PUBLIC_API_URL required)
│   └── check-i18n-keys.mjs      # CI parity check (es ↔ en)
├── static/                       # static assets (favicon, etc.)
└── svelte.config.js              # adapter-static, fallback index.html
```

## Local development

```bash
# 1. Install
npm install

# 2. Copy the env example and edit with your values
cp .env.example .env

# 3. Start dev server (http://localhost:5173)
npm run dev
```

`.env` (Vite loads `PUBLIC_*` vars into the browser bundle):

```ini
PUBLIC_API_URL=https://asistcv-backend.onrender.com
PUBLIC_BACKEND_API_KEY=<your key from Render's BACKEND_API_KEY>
```

`PUBLIC_BACKEND_API_KEY` may be left empty if the backend is running in open
mode (no `BACKEND_API_KEY` set on the backend).

## Build for production

```bash
npm run build
```

The prebuild script (`scripts/check-env.mjs`) fails the build if `PUBLIC_API_URL`
is missing. Output goes to `build/` (HTML + JS + assets), ready for any static
host.

Preview locally:

```bash
npm run preview
# → http://localhost:4173
```

## Type / Svelte smoke

```bash
npm run check
```

Runs `svelte-kit sync` + `svelte-check` against the TS config. Zero errors is
the gate.

## Environment variables

| Variable | Required | When | Purpose |
|---|---|---|---|
| `PUBLIC_API_URL` | yes (build) | build | Backend base URL. The build fails if missing. |
| `PUBLIC_BACKEND_API_KEY` | only if backend is in protected mode | build | Sent as `Authorization: Bearer …` on every request. |

The `PUBLIC_` prefix is mandatory — only those vars are inlined into the client
bundle by SvelteKit/Vite.

## Deployment — Cloudflare Pages

The app is built as a static SPA and served from Cloudflare Pages.

1. **Create the project** in Cloudflare dashboard:
   - **Connect to Git** → pick the AsistCV repo.
   - **Framework preset**: SvelteKit (or "None" — adapter-static handles it).
   - **Build command**: `cd frontend && npm install && npm run build`
   - **Build output directory**: `frontend/build`
   - **Root directory**: leave blank (the build command does `cd frontend`).

2. **Environment variables** (Settings → Build → Environment variables):

   | Variable | Value |
   |---|---|
   | `PUBLIC_API_URL` | `https://asistcv-backend.onrender.com` |
   | `PUBLIC_BACKEND_API_KEY` | value matching the backend's `BACKEND_API_KEY` |

3. **SPA routing**: the adapter-static config emits `index.html` as the fallback
   for unknown routes, so `/history/{id}` resolves client-side. No `_redirects`
   file needed.

4. **CORS**: after the first deploy, copy the Pages URL (e.g.
   `https://asistcv-frontend.pages.dev`) into the backend's `CORS_ORIGINS` env
   var in Render. See [`docs/CORS_NOTES.md`](docs/CORS_NOTES.md) for details.

5. **Custom domain** (optional): Pages → Custom domains → add. Update
   `CORS_ORIGINS` on the backend with the new origin.

## Adding a new language

1. **Create the catalog** as a flat object mirroring `es.json`'s structure:

   ```bash
   cp src/lib/i18n/locales/es.json src/lib/i18n/locales/pt.json
   # edit pt.json — translate every value, keep keys 1:1
   ```

2. **Register the locale** in `src/lib/i18n/index.ts`:

   ```ts
   const SUPPORTED = ['es', 'en', 'pt'] as const;
   // ...
   addMessages('pt', pt);
   init({ fallbackLocale: 'es', initialLocale: detectInitial() });
   // extend detectInitial() so a Portuguese browser maps to 'pt'
   ```

3. **Add a button / link** in `LanguageToggle.svelte` (or build a dropdown).

4. **Update CI**: `frontend/scripts/check-i18n-keys.mjs` already iterates over
   every locale in `REQUIRED_LOCALES`; add `'pt'` to that array to enforce
   parity with the canonical `es.json`.

5. **Update the PR template / docs** if there's a checklist to tick.

## CI

Two CI hooks live in `.github/workflows/ci.yml`:

- **`frontend-i18n-parity`** (job): runs `npm ci && node scripts/check-i18n-keys.mjs`
  in `frontend/`. Fails if any locale is missing keys vs the canonical Spanish
  catalog, or if any value is empty.
- **`prebuild` script** (`scripts/check-env.mjs`): runs on `npm run build` and
  fails if `PUBLIC_API_URL` is missing.

See [`docs/CI_SETUP.md`](../docs/CI_SETUP.md) for the full pipeline.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| Build fails with "Faltan variables ... PUBLIC_API_URL" | `PUBLIC_API_URL` not set in Cloudflare Pages build env. |
| 401 in browser after deploy | `PUBLIC_BACKEND_API_KEY` mismatch with backend's `BACKEND_API_KEY`, or backend in protected mode without key. |
| Network errors / CORS errors | Backend's `CORS_ORIGINS` doesn't include the Pages domain. See `docs/CORS_NOTES.md`. |
| `npm run check` flags a `$api/types` import | Run `npm run check:watch` once; the `.svelte-kit/` types may need regenerating. |

## License

See [`../LICENSE`](../LICENSE).