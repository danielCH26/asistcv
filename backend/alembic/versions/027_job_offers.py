"""027_job_offers: tabla job_offers + RLS + users.offer_preferences JSONB.

Tabla job_offers — almacena ofertas de trabajo descubiertas por Tavily:
  - id (PK, serial)
  - owner_user_id (FK users.id NOT NULL)
  - title (VARCHAR NOT NULL)
  - company (VARCHAR nullable)
  - url (VARCHAR NOT NULL — dedupe key: una oferta por usuario+url)
  - snippet (TEXT nullable)
  - published_date (VARCHAR nullable — Tavily la devuelve frecuentemente nula)
  - score (INTEGER nullable — ranking del pipeline de matching)
  - status (VARCHAR NOT NULL default 'new' — valores: new | archived)
  - search_query (TEXT nullable — auditoría: query que descubrió la oferta)
  - created_at (TIMESTAMPTZ default now())

Índices:
  - (owner_user_id, created_at) — listados por usuario ordenados por fecha
  - (owner_user_id, url) — dedupe local: un mismo url no se reinserta

RLS habilitado desde el día uno (patrón de 011/023):
  - ENABLE + FORCE ROW LEVEL SECURITY (FORCE: ni el table owner lee sin contexto)
  - job_offers_service_all: carve-out del service principal (GUC '0')
  - job_offers_owner_{select,insert,update,delete}: owner_user_id =
    public.app_current_user_id()

Columna users.offer_preferences JSONB nullable — contiene:
  - frequency_hours (int, default 24)
  - top_n (int, default 5)
  - filters (object)
  - email_frequency (string)
  El default lo maneja la app, no la DB.

Downgrade: dropea policies, desactiva RLS, y revierte offer_preferences.
La tabla job_offers se conserva en downgrade (no se dropea en esta revisión;
una migración posterior dedicada la eliminará si se decide abortar).
"""

from collections.abc import Sequence

from alembic import op

revision: str = "027_job_offers"
down_revision: str = "026_embedding_dim_768"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

_TABLE = "job_offers"
_USERS_TABLE = "users"

_UPGRADE_STATEMENTS = [
    # --- Tabla job_offers ---
    f"""
    CREATE TABLE IF NOT EXISTS public.{_TABLE} (
        id                SERIAL PRIMARY KEY,
        owner_user_id     INTEGER NOT NULL
                            REFERENCES public.{_USERS_TABLE}(id)
                            ON DELETE CASCADE,
        title             VARCHAR(500) NOT NULL,
        company           VARCHAR(255),
        url               VARCHAR(2048) NOT NULL,
        snippet           TEXT,
        published_date    VARCHAR(100),
        score             INTEGER,
        status            VARCHAR(20) NOT NULL DEFAULT 'new',
        search_query      TEXT,
        created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    # Índice para listados ordenados por fecha
    f"CREATE INDEX IF NOT EXISTS idx_{_TABLE}_owner_created "
    f"ON public.{_TABLE} (owner_user_id, created_at DESC)",
    # Índice para dedupe local por (owner, url)
    f"CREATE UNIQUE INDEX IF NOT EXISTS idx_{_TABLE}_owner_url "
    f"ON public.{_TABLE} (owner_user_id, url)",
    # --- RLS ---
    f"ALTER TABLE public.{_TABLE} ENABLE ROW LEVEL SECURITY",
    f"ALTER TABLE public.{_TABLE} FORCE ROW LEVEL SECURITY",
    # Service carve-out (MCP adapter / open mode): GUC '0' lo pasa.
    f"CREATE POLICY {_TABLE}_service_all ON public.{_TABLE} FOR ALL "
    f"USING (current_setting('app.current_user_id', true) = '0')",
    # Owner: solo sus filas. app_current_user_id() devuelve NULL sin GUC
    # (default DENY con FORCE).
    f"CREATE POLICY {_TABLE}_owner_select ON public.{_TABLE} "
    f"FOR SELECT USING (owner_user_id = public.app_current_user_id())",
    f"CREATE POLICY {_TABLE}_owner_insert ON public.{_TABLE} "
    f"FOR INSERT WITH CHECK (owner_user_id = public.app_current_user_id())",
    f"CREATE POLICY {_TABLE}_owner_update ON public.{_TABLE} "
    f"FOR UPDATE USING (owner_user_id = public.app_current_user_id()) "
    f"WITH CHECK (owner_user_id = public.app_current_user_id())",
    f"CREATE POLICY {_TABLE}_owner_delete ON public.{_TABLE} "
    f"FOR DELETE USING (owner_user_id = public.app_current_user_id())",
    # --- users.offer_preferences ---
    f"ALTER TABLE public.{_USERS_TABLE} "
    f"ADD COLUMN IF NOT EXISTS offer_preferences JSONB",
]

_DOWNGRADE_STATEMENTS = [
    f"ALTER TABLE public.{_USERS_TABLE} DROP COLUMN IF EXISTS offer_preferences",
    f"DROP POLICY IF EXISTS {_TABLE}_owner_delete ON public.{_TABLE}",
    f"DROP POLICY IF EXISTS {_TABLE}_owner_update ON public.{_TABLE}",
    f"DROP POLICY IF EXISTS {_TABLE}_owner_insert ON public.{_TABLE}",
    f"DROP POLICY IF EXISTS {_TABLE}_owner_select ON public.{_TABLE}",
    f"DROP POLICY IF EXISTS {_TABLE}_service_all ON public.{_TABLE}",
    f"ALTER TABLE public.{_TABLE} NO FORCE ROW LEVEL SECURITY",
    f"ALTER TABLE public.{_TABLE} DISABLE ROW LEVEL SECURITY",
    f"DROP INDEX IF EXISTS idx_{_TABLE}_owner_url",
    f"DROP INDEX IF EXISTS idx_{_TABLE}_owner_created",
    # La tabla se deja intacta en downgrade (decisión de diseño:
    # persiste; se elimina en una migración explícita si se aborta).
]


def upgrade() -> None:
    for stmt in _UPGRADE_STATEMENTS:
        op.execute(stmt.strip())


def downgrade() -> None:
    for stmt in _DOWNGRADE_STATEMENTS:
        op.execute(stmt.strip())
