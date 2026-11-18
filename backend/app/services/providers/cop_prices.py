"""
Precios de los planes en pesos colombianos (COP).

El catálogo oficial (`PLANS_CATALOG` en `app/api/v1/billing.py`) está en
USD cents porque las pasarelas globales (Lemon Squeezy, Stripe) cobran en
dólares. Las pasarelas colombianas (Wompi, Mercado Pago) cobran en COP, así
que necesitan su propia tabla.

Una sola tabla para las dos, porque si cada provider lleva la suya los
montos se desalinean y el usuario ve precios distintos según el botón que
pulse.

OJO con las unidades — es la trampa clásica:
  - Wompi pide ``amount_in_cents`` → centavos (29.000 COP = 2.900.000).
  - Mercado Pago pide ``unit_price`` → pesos enteros (29.000).
Por eso acá se guarda el precio en PESOS y cada provider convierte.

Los valores coinciden con los precios en USD del catálogo (a ~4.000 COP/USD):
  job_seeker_monthly  $9 USD  → 29.000 COP
  recruiter_starter   $29 USD → 99.000 COP
  recruiter_business  $99 USD → 199.000 COP
  recruiter_agency   $299 USD → 499.000 COP
"""

from __future__ import annotations

# Precio del plan en pesos colombianos (COP), no en centavos.
PLAN_PRICES_COP: dict[str, int] = {
    "job_seeker_monthly": 29_000,
    "recruiter_starter": 99_000,
    "recruiter_business": 199_000,
    "recruiter_agency": 499_000,
}

# Plan que se cobra si el catálogo no trae un plan_id reconocible.
DEFAULT_PRICE_COP = 29_000


def cop_price(plan_id: str) -> int:
    """Precio del plan en pesos colombianos (COP)."""
    return PLAN_PRICES_COP.get(plan_id, DEFAULT_PRICE_COP)


def cop_amount_cents(plan_id: str) -> int:
    """Precio del plan en centavos (lo que pide Wompi)."""
    return cop_price(plan_id) * 100
