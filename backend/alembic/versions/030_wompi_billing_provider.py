"""
029_wompi_billing_provider: permite 'wompi' en las tablas de billing.

La migración 028 creó `payment_methods` y `payment_webhook_events` con un
CHECK sobre `provider` limitado a ('stripe', 'lemon_squeezy', 'mercadopago').
Ese CHECK rechazaba los eventos de Wompi con un CheckViolationError → el
endpoint del webhook devolvía 500 y la suscripción NUNCA se activaba: el
usuario pagaba y su plan no cambiaba.

Acá se reemplazan los dos CHECK por los que incluyen 'wompi'. No se cambia
nada más: las columnas, los índices, las políticas RLS y los datos siguen
igual.

Downgrade: vuelve el CHECK original (y con él, Wompi vuelve a fallar — es
lo esperado al revertir).
"""

from collections.abc import Sequence

from alembic import op

revision: str = "029_wompi_billing_provider"
down_revision: str = "028_payment_methods"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

_TABLE_PM = "payment_methods"
_TABLE_PWE = "payment_webhook_events"

_PROVIDERS_WITH_WOMPI = "'stripe', 'lemon_squeezy', 'mercadopago', 'wompi'"
_PROVIDERS_ORIGINAL = "'stripe', 'lemon_squeezy', 'mercadopago'"


def _swap_provider_check(table: str, providers: str) -> list[str]:
    """Reemplaza el CHECK de provider de una tabla de billing."""
    constraint = f"chk_{table}_provider"
    return [
        f"ALTER TABLE public.{table} DROP CONSTRAINT IF EXISTS {constraint}",
        f"ALTER TABLE public.{table} ADD CONSTRAINT {constraint} "
        f"CHECK (provider IN ({providers}))",
    ]


_UPGRADE_STATEMENTS = [
    *_swap_provider_check(_TABLE_PM, _PROVIDERS_WITH_WOMPI),
    *_swap_provider_check(_TABLE_PWE, _PROVIDERS_WITH_WOMPI),
]

_DOWNGRADE_STATEMENTS = [
    *_swap_provider_check(_TABLE_PM, _PROVIDERS_ORIGINAL),
    *_swap_provider_check(_TABLE_PWE, _PROVIDERS_ORIGINAL),
]


def upgrade() -> None:
    for statement in _UPGRADE_STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    for statement in _DOWNGRADE_STATEMENTS:
        op.execute(statement)
