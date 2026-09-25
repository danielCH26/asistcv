"""Row-Level Security policies for user-owned tables (Sprint 2, PR6).

Revision ID: 011_rls_policies
Revises: 010_subscriptions_user_fk
Create Date: 2026-09-24

SECURITY-CRITICAL migration: enforces per-user data isolation at the
database level (strict CV isolation, cv-management spec R6).

Bypass mechanism (ONE mechanism, documented here):
    The GUC ``app.current_user_id = '0'`` is the SERVICE context. One
    PERMISSIVE ``FOR ALL`` policy per protected table grants full access
    when the GUC equals '0'. It is set server-side only (never from
    client input) for:
      - MCP adapter / API-key requests (CurrentUser id=0),
      - the internal audit-retention cron endpoint,
      - Stripe webhook handlers (no user principal exists).
    Anonymous free-audit flows set the GUC to 'anonymous' instead; the
    audit_uploads policies accept that value for unlinked rows only.

Every session change uses ``SET LOCAL`` (transaction-scoped) so pooled
connections never leak context between transactions.

Tables intentionally NOT protected in this migration:
    - users: login/signup run BEFORE any user context exists (login looks
      a user up by email with no GUC); a self-row policy would break
      authentication. Defense in depth for users stays at the endpoint
      layer. Revisit with a dedicated provisioning context.
    - users_refresh_tokens, token_revocation, auth_login_attempts,
      auth_security_events: auth plumbing keyed by opaque hashes; no
      cross-user read path is exposed this sprint.
    - profiles: legacy single-user table; no owner assignment exists on
      its create path yet (match/profile flows still treat it as shared
      in service mode). Deferred until profile CRUD becomes user-bound.
    - audit_funnel_events, recruiter_audit_log, stripe_webhook_events:
      telemetry / append-only (trigger-protected) / internal ledger.
    - job_descriptions: shared JD corpus.

Owner-expression helper ``public.app_current_user_id()`` returns the GUC
parsed as int, or NULL when the GUC is unset/non-numeric, so policies
default to DENY (FORCE RLS means even the table owner cannot read
without context).
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "011_rls_policies"
down_revision: str = "010_subscriptions_user_fk"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

# table -> owner column
_OWNER_TABLES: dict[str, str] = {
    "users_cvs": "owner_user_id",
    "analyses": "owner_user_id",
    "recruiter_candidates": "recruiter_id",
    "recruiter_analyses": "recruiter_id",
    "recruiter_consents": "user_id",
    "subscriptions": "user_id",
    "payments": "user_id",
    "usage_counters": "user_id",
}

# Table protected with a parent-join policy: rows are reachable only
# through recruiter_candidates (recruiter_id), or while the row is an
# in-transaction orphan (candidate_id IS NULL during the create flow:
# CV row is flushed before its candidate row exists).
_CV_CHILD_TABLE = "recruiter_candidates_cvs"

_ANONYMOUS_TABLE = "audit_uploads"

_FUNCTION_DDL = """
CREATE OR REPLACE FUNCTION public.app_current_user_id() RETURNS integer
LANGUAGE sql STABLE
AS $fn$
  SELECT CASE
    WHEN current_setting('app.current_user_id', true) ~ '^[0-9]+$'
    THEN current_setting('app.current_user_id', true)::integer
    ELSE NULL
  END
$fn$
"""

_DROP_FUNCTION_DDL = "DROP FUNCTION IF EXISTS public.app_current_user_id()"


def _enable_force(table: str) -> list[str]:
    return [
        f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY",
        f"ALTER TABLE public.{table} FORCE ROW LEVEL SECURITY",
    ]


def _disable_force(table: str) -> list[str]:
    return [
        f"ALTER TABLE public.{table} NO FORCE ROW LEVEL SECURITY",
        f"ALTER TABLE public.{table} DISABLE ROW LEVEL SECURITY",
    ]


def _service_policy(table: str) -> str:
    return (
        f"CREATE POLICY {table}_service_all ON public.{table} FOR ALL "
        f"USING (current_setting('app.current_user_id', true) = '0')"
    )


def _owner_policies(table: str, column: str) -> list[str]:
    uid = "public.app_current_user_id()"
    return [
        f"CREATE POLICY {table}_owner_select ON public.{table} "
        f"FOR SELECT USING ({column} = {uid})",
        f"CREATE POLICY {table}_owner_insert ON public.{table} "
        f"FOR INSERT WITH CHECK ({column} = {uid})",
        f"CREATE POLICY {table}_owner_update ON public.{table} "
        f"FOR UPDATE USING ({column} = {uid}) WITH CHECK ({column} = {uid})",
        f"CREATE POLICY {table}_owner_delete ON public.{table} "
        f"FOR DELETE USING ({column} = {uid})",
    ]


def _cv_child_policies() -> list[str]:
    table = _CV_CHILD_TABLE
    reachable = (
        f"({table}.candidate_id IS NULL OR EXISTS ("
        f"SELECT 1 FROM public.recruiter_candidates AS rc "
        f"WHERE rc.id = {table}.candidate_id "
        f"AND rc.recruiter_id = public.app_current_user_id()))"
    )
    return [
        _service_policy(table),
        f"CREATE POLICY {table}_owner_select ON public.{table} "
        f"FOR SELECT USING ({reachable})",
        f"CREATE POLICY {table}_owner_insert ON public.{table} "
        f"FOR INSERT WITH CHECK ({reachable})",
        f"CREATE POLICY {table}_owner_update ON public.{table} "
        f"FOR UPDATE USING ({reachable}) WITH CHECK ({reachable})",
        f"CREATE POLICY {table}_owner_delete ON public.{table} "
        f"FOR DELETE USING ({reachable})",
    ]


def _audit_policies() -> list[str]:
    table = _ANONYMOUS_TABLE
    uid = "public.app_current_user_id()"
    guc = "current_setting('app.current_user_id', true)"
    anonymous = f"USING ({table}.linked_user_id IS NULL AND {guc} = 'anonymous')"
    anonymous_check = (
        f"WITH CHECK ({table}.linked_user_id IS NULL "
        f"OR {table}.linked_user_id = {uid})"
    )
    owner = (
        f"USING ({table}.linked_user_id IS NOT NULL "
        f"AND {table}.linked_user_id = {uid})"
    )
    owner_check = f"WITH CHECK ({table}.linked_user_id = {uid})"
    return [
        _service_policy(table),
        # Anonymous funnel: unlinked rows only (write, read-back, capture).
        f"CREATE POLICY {table}_anonymous_all ON public.{table} FOR ALL "
        f"{anonymous} {anonymous_check}",
        # Claimed rows: owner-only (linked_user_id set via service context).
        f"CREATE POLICY {table}_owner_all ON public.{table} FOR ALL "
        f"{owner} {owner_check}",
    ]


def upgrade() -> None:
    op.execute(sa.text(_FUNCTION_DDL))

    statements: list[str] = []
    for table in _OWNER_TABLES:
        statements += _enable_force(table)
        statements.append(_service_policy(table))
        statements += _owner_policies(table, _OWNER_TABLES[table])

    statements += _enable_force(_CV_CHILD_TABLE)
    statements += _cv_child_policies()

    statements += _enable_force(_ANONYMOUS_TABLE)
    statements += _audit_policies()

    for stmt in statements:
        op.execute(sa.text(stmt))


def downgrade() -> None:
    """Revert in reverse order: policies, FORCE/ENABLE, helper function."""
    statements: list[str] = []

    for table in (_ANONYMOUS_TABLE, _CV_CHILD_TABLE):
        for suffix in (
            "owner_select",
            "owner_insert",
            "owner_update",
            "owner_delete",
            "anonymous_all",
            "owner_all",
            "service_all",
        ):
            statements.append(
                f"DROP POLICY IF EXISTS {table}_{suffix} ON public.{table}"
            )
        statements += _disable_force(table)

    for table in reversed(list(_OWNER_TABLES)):
        for suffix in ("delete", "update", "insert", "select"):
            statements.append(
                f"DROP POLICY IF EXISTS {table}_owner_{suffix} ON public.{table}"
            )
        statements.append(
            f"DROP POLICY IF EXISTS {table}_service_all ON public.{table}"
        )
        statements += _disable_force(table)

    statements.append(_DROP_FUNCTION_DDL)

    for stmt in statements:
        op.execute(sa.text(stmt))
