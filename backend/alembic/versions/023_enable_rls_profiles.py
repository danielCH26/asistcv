"""Enable ROW LEVEL SECURITY on ``profiles`` (issue #95, follow-up de #87).

La migración 011 difirió ``profiles`` explícitamente: *"Deferred until
profile CRUD becomes user-bound"*. El fix de #85 cumplió la precondición
(``owner_user_id`` estampado en create con JWT real obligatorio), así que
esta migración aplica el MISMO patrón que la 011 usa para las demás tablas
de owner:

- ENABLE + FORCE RLS (FORCE: ni el table owner lee sin contexto).
- ``profiles_service_all``: el carve-out del service principal (GUC '0')
  se conserva a nivel DB — el MCP adapter y el modo abierto dependen de él
  (issue #87: queda auditable vía el log de ``_get_profile_or_404``).
- ``profiles_owner_select/insert/update/delete``: el owner solo ve y toca
  sus filas, vía ``public.app_current_user_id()`` (función de la 011, ya
  desplegada en todas las bases que corrieron 011).

Defense in depth: los filtros ``owner_user_id == user.id`` a nivel
endpoint (issue #85) quedan — RLS es la segunda capa, no el reemplazo.

Downgrade: dropea las policies y desactiva RLS (los datos no se tocan).
"""

from collections.abc import Sequence

from alembic import op

revision: str = "023_enable_rls_profiles"
down_revision: str = "022_cv_adaptations_cv_ver"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

_TABLE = "profiles"

_UPGRADE_STATEMENTS = [
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
]

_DOWNGRADE_STATEMENTS = [
    f"DROP POLICY IF EXISTS {_TABLE}_owner_delete ON public.{_TABLE}",
    f"DROP POLICY IF EXISTS {_TABLE}_owner_update ON public.{_TABLE}",
    f"DROP POLICY IF EXISTS {_TABLE}_owner_insert ON public.{_TABLE}",
    f"DROP POLICY IF EXISTS {_TABLE}_owner_select ON public.{_TABLE}",
    f"DROP POLICY IF EXISTS {_TABLE}_service_all ON public.{_TABLE}",
    f"ALTER TABLE public.{_TABLE} NO FORCE ROW LEVEL SECURITY",
    f"ALTER TABLE public.{_TABLE} DISABLE ROW LEVEL SECURITY",
]


def upgrade() -> None:
    for statement in _UPGRADE_STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    for statement in _DOWNGRADE_STATEMENTS:
        op.execute(statement)
