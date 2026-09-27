"""Row-Level Security policies for ``cv_adaptations`` (Slice A foundation).

Revision ID: 016_rls_cv_adaptations
Revises: 015_cv_adaptations
Create Date: 2026-09-27

SECURITY-CRITICAL migration (cv-adaptation spec R6, cv-management R2):
per-user isolation at the database level.

Bypass mechanism (mirrors migration 011)
----------------------------------------
The GUC ``app.current_user_id = '0'`` is the SERVICE context. One
``FOR ALL`` permissive policy grants full access when the GUC equals
'0'. Reserved for server-side callers only:

* the internal retention sweeper (``POST /internal/adaptations/cleanup``
  in PR3);
* future maintenance jobs that touch rows across users.

``CurrentUser(id=0)`` is already produced by ``get_db()`` in
``app/api/deps.py`` for API-key sessions, so the bypass path is
reachable without new infra.

Owner policies (one per verb)
-----------------------------
Per-user policies match ``owner_user_id = public.app_current_user_id()``
(created in migration 011). It returns the GUC parsed as int, or NULL
when unset/non-numeric, so policies default to DENY (``FORCE ROW
LEVEL SECURITY`` means even the table owner is filtered).
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "016_rls_cv_adaptations"
down_revision: str | Sequence[str] | None = "015_cv_adaptations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "cv_adaptations"


def _enable_force() -> list[str]:
    return [
        f"ALTER TABLE public.{_TABLE} ENABLE ROW LEVEL SECURITY",
        f"ALTER TABLE public.{_TABLE} FORCE ROW LEVEL SECURITY",
    ]


def _disable_force() -> list[str]:
    return [
        f"ALTER TABLE public.{_TABLE} NO FORCE ROW LEVEL SECURITY",
        f"ALTER TABLE public.{_TABLE} DISABLE ROW LEVEL SECURITY",
    ]


def _service_policy() -> str:
    return (
        f"CREATE POLICY {_TABLE}_service_all ON public.{_TABLE} FOR ALL "
        "USING (current_setting('app.current_user_id', true) = '0')"
    )


def _owner_policies() -> list[str]:
    uid = "public.app_current_user_id()"
    return [
        # SELECT — no WITH CHECK needed.
        f"CREATE POLICY {_TABLE}_owner_select ON public.{_TABLE} "
        f"FOR SELECT USING (owner_user_id = {uid})",
        # INSERT — only WITH CHECK (new rows must satisfy the predicate).
        f"CREATE POLICY {_TABLE}_owner_insert ON public.{_TABLE} "
        f"FOR INSERT WITH CHECK (owner_user_id = {uid})",
        # UPDATE — USING + WITH CHECK (must own row before and after).
        f"CREATE POLICY {_TABLE}_owner_update ON public.{_TABLE} "
        f"FOR UPDATE USING (owner_user_id = {uid}) "
        f"WITH CHECK (owner_user_id = {uid})",
        # DELETE — only USING.
        f"CREATE POLICY {_TABLE}_owner_delete ON public.{_TABLE} "
        f"FOR DELETE USING (owner_user_id = {uid})",
    ]


def upgrade() -> None:
    """Enable RLS, install service bypass + four owner policies."""
    for stmt in _enable_force() + [_service_policy()] + _owner_policies():
        op.execute(sa.text(stmt))


def downgrade() -> None:
    """Revert in reverse order: drop policies, then disable FORCE / RLS."""
    drops = [
        f"DROP POLICY IF EXISTS {_TABLE}_owner_delete ON public.{_TABLE}",
        f"DROP POLICY IF EXISTS {_TABLE}_owner_update ON public.{_TABLE}",
        f"DROP POLICY IF EXISTS {_TABLE}_owner_insert ON public.{_TABLE}",
        f"DROP POLICY IF EXISTS {_TABLE}_owner_select ON public.{_TABLE}",
        f"DROP POLICY IF EXISTS {_TABLE}_service_all ON public.{_TABLE}",
    ]
    for stmt in drops + _disable_force():
        op.execute(sa.text(stmt))
