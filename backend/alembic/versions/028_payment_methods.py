"""
028_payment_methods: payment_methods + payment_webhook_events + RLS.

payment_methods — stores a normalised view of the user's payment method
across all providers (Stripe, Lemon Squeezy, Mercado Pago). One row per
active subscription; a new row replaces the old one on plan-change.
RLS is enabled day one (pattern of 023/027) so every query via the
user-facing API respects ownership without extra WHERE clauses.

payment_webhook_events — idempotency ledger shared by all providers
(except Stripe which keeps stripe_webhook_events until a dedicated
migration moves it). No RLS: the service writes via set_rls_service
and the table is append-only from the server side.

Downgrade: drop payment_webhook_events first (no FK), then payment_methods
(no FK either but it is the FK target of nothing so order is safe).
"""

from collections.abc import Sequence

from alembic import op

revision: str = "028_payment_methods"
down_revision: str = "027_job_offers"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

_TABLE_PM = "payment_methods"
_TABLE_PWE = "payment_webhook_events"
_USERS_TABLE = "users"

_UPGRADE_STATEMENTS = [
    # --- payment_methods ---
    f"""
    CREATE TABLE IF NOT EXISTS public.{_TABLE_PM} (
        id                          SERIAL PRIMARY KEY,
        user_id                     INTEGER NOT NULL
                                      REFERENCES public.{_USERS_TABLE}(id)
                                      ON DELETE CASCADE,
        provider                    VARCHAR(30) NOT NULL,
        provider_customer_id        VARCHAR(100),
        provider_subscription_id    VARCHAR(100) UNIQUE,
        status                      VARCHAR(20) NOT NULL,
        plan_id                     VARCHAR(50) NOT NULL,
        current_period_end          TIMESTAMPTZ,
        created_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT chk_payment_methods_provider
          CHECK (provider IN ('stripe', 'lemon_squeezy', 'mercadopago'))
    )
    """,
    f"CREATE INDEX IF NOT EXISTS idx_{_TABLE_PM}_user_id "
    f"ON public.{_TABLE_PM} (user_id)",
    f"CREATE INDEX IF NOT EXISTS idx_{_TABLE_PM}_provider_sub_id "
    f"ON public.{_TABLE_PM} (provider, provider_subscription_id)",
    # --- RLS on payment_methods ---
    f"ALTER TABLE public.{_TABLE_PM} ENABLE ROW LEVEL SECURITY",
    f"ALTER TABLE public.{_TABLE_PM} FORCE ROW LEVEL SECURITY",
    # Service carve-out: GUC '0' bypasses all policy checks.
    f"CREATE POLICY {_TABLE_PM}_service_all ON public.{_TABLE_PM} FOR ALL "
    f"USING (current_setting('app.current_user_id', true) = '0')",
    # Owner: rows where owner_user_id matches the session user.
    f"CREATE POLICY {_TABLE_PM}_owner_select ON public.{_TABLE_PM} "
    f"FOR SELECT USING (user_id = public.app_current_user_id())",
    f"CREATE POLICY {_TABLE_PM}_owner_insert ON public.{_TABLE_PM} "
    f"FOR INSERT WITH CHECK (user_id = public.app_current_user_id())",
    f"CREATE POLICY {_TABLE_PM}_owner_update ON public.{_TABLE_PM} "
    f"FOR UPDATE USING (user_id = public.app_current_user_id()) "
    f"WITH CHECK (user_id = public.app_current_user_id())",
    f"CREATE POLICY {_TABLE_PM}_owner_delete ON public.{_TABLE_PM} "
    f"FOR DELETE USING (user_id = public.app_current_user_id())",
    # --- payment_webhook_events ---
    f"""
    CREATE TABLE IF NOT EXISTS public.{_TABLE_PWE} (
        id              SERIAL PRIMARY KEY,
        provider        VARCHAR(30) NOT NULL,
        event_id        VARCHAR(100) NOT NULL,
        type            VARCHAR(50) NOT NULL,
        payload_json    JSONB,
        processed_at    TIMESTAMPTZ,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT chk_{_TABLE_PWE}_provider CHECK (provider IN ('stripe', 'lemon_squeezy', 'mercadopago'))
    )
    """,
    # Idempotency: same provider + event_id must not be inserted twice.
    f"CREATE UNIQUE INDEX IF NOT EXISTS idx_{_TABLE_PWE}_provider_event_id "
    f"ON public.{_TABLE_PWE} (provider, event_id)",
]

_DOWNGRADE_STATEMENTS = [
    f"DROP INDEX IF EXISTS idx_{_TABLE_PWE}_provider_event_id",
    f"DROP TABLE IF EXISTS public.{_TABLE_PWE}",
    f"DROP POLICY IF EXISTS {_TABLE_PM}_owner_delete ON public.{_TABLE_PM}",
    f"DROP POLICY IF EXISTS {_TABLE_PM}_owner_update ON public.{_TABLE_PM}",
    f"DROP POLICY IF EXISTS {_TABLE_PM}_owner_insert ON public.{_TABLE_PM}",
    f"DROP POLICY IF EXISTS {_TABLE_PM}_owner_select ON public.{_TABLE_PM}",
    f"DROP POLICY IF EXISTS {_TABLE_PM}_service_all ON public.{_TABLE_PM}",
    f"ALTER TABLE public.{_TABLE_PM} NO FORCE ROW LEVEL SECURITY",
    f"ALTER TABLE public.{_TABLE_PM} DISABLE ROW LEVEL SECURITY",
    f"DROP INDEX IF EXISTS idx_{_TABLE_PM}_provider_sub_id",
    f"DROP INDEX IF EXISTS idx_{_TABLE_PM}_user_id",
    f"DROP TABLE IF EXISTS public.{_TABLE_PM}",
]


def upgrade() -> None:
    for stmt in _UPGRADE_STATEMENTS:
        op.execute(stmt.strip())


def downgrade() -> None:
    for stmt in _DOWNGRADE_STATEMENTS:
        op.execute(stmt.strip())
