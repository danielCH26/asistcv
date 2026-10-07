# Infrastructure

Infraestructura local de desarrollo para AsistCV. Los deploys de producción y
staging son gestionados por plataforma (backend en Render, frontend en
Cloudflare Pages) y no requieren archivos de configuración en este directorio.

> **Histórico.** El stack original (pre-migración, septiembre 2026) usaba GCP
> (Cloud Run, Cloud SQL, Cloud Build, Artifact Registry, Terraform). Esa
> configuración nunca llegó a deployarse por el requisito de tarjeta de
> crédito de GCP y fue reemplazada por el stack free tier actual. Detalle en
> [`STACK.md`](../STACK.md) y [`docs/DEPLOY.md`](../DEPLOY.md).

## Contenido

- `docker-compose.yml` — levanta Postgres 16 con pgvector en local (host port **5433** → container 5432).
- `.env.example` — plantilla de variables para la DB local. Copiar a `.env` si querés sobreescribir credenciales.

## Servicios

| Servicio | Destino | Notas |
|---|---|---|
| Frontend (SvelteKit) | Cloudflare Pages | Auto-deploy desde `main`. |
| Backend (FastAPI) | Render Web Service | Auto-deploy desde `main`. Free tier con cold start. |
| Base de datos | Neon (prod) / docker-compose (local) | Postgres + pgvector. |
| CI | GitHub Actions | Tests + lint + build por push y por PR. |

## Desarrollo local

```bash
# Levantar la DB local (Postgres + pgvector)
make db-up

# Aplicar migraciones
make migrate

# Detener la DB
make db-down
```

El `docker-compose.yml` publica la DB en el host port **5433** (no el 5432
por defecto de Postgres) para evitar colisiones con una instalación local de
Postgres. La URL que usa el backend por defecto es
`postgresql://asistcv:asistcv@localhost:5433/asistcv` — ver
[`backend/.env.example`](../backend/.env.example).

## Deploy

El deploy es automático: push a `main` → CI green → Render (backend) y
Cloudflare Pages (frontend) despliegan solos. No hay scripts de deploy en
este repo. Para el detalle de env vars de producción y troubleshooting, ver
[`docs/DEPLOY.md`](../DEPLOY.md).
