"""Allow an authenticated principal to claim an unlinked ``audit_uploads`` row.

Revision ID: 018_audit_claim_policy
Revises: 017_usage_counters_adaptations
Create Date: 2026-09-29

SECURITY-CRITICAL migration (audit funnel, S3 IDOR fix).

Why
---
``POST /v1/audit/{token}/claim`` used to run under the SERVICE RLS context
(``app.current_user_id = '0'``) because no policy admitted a user
principal on an unlinked row: migration 011 only grants ``'0'`` (service),
``'anonymous'`` and rows already owned by the caller. That is what made
the endpoint an unauthenticated cross-user write.

The fix moves the claim to the caller's own context
(``set_rls_user(session, current_user.id, current_user.role)``), which
only works if the database admits the anonymous -> owner transition for a
numeric principal. This migration opens exactly that transition and
nothing else:

* ``audit_uploads_claim_select``: a real user principal (the helper
  returns NULL for the unset / 'anonymous' markers, so those principals
  are excluded) may READ unlinked rows. The audit token is the
  capability, exactly as in the anonymous funnel.
* ``audit_uploads_claim_update``: a user may UPDATE an unlinked row, but
  ``WITH CHECK`` pins the result to ``app_current_user_id()``. A caller
  therefore cannot link an audit to a *different* account, and cannot
  re-link one that is already owned.

There is deliberately no claim INSERT or DELETE policy: creating audits
stays on the anonymous funnel and purging them stays on the retention cron
(service context).

Net effect at the database layer: the claim can no longer be a
cross-user write, whether or not the endpoint authenticates the caller.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "018_audit_claim_policy"
down_revision: str | Sequence[str] | None = "017_usage_counters_adaptations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "audit_uploads"


def upgrade() -> None:
    uid = "public.app_current_user_id()"
    op.execute(sa.text(
        f"CREATE POLICY {_TABLE}_claim_select ON public.{_TABLE} "
        f"FOR SELECT USING (linked_user_id IS NULL AND {uid} IS NOT NULL)"
    ))
    op.execute(sa.text(
        f"CREATE POLICY {_TABLE}_claim_update ON public.{_TABLE} "
        f"FOR UPDATE USING (linked_user_id IS NULL) "
        f"WITH CHECK (linked_user_id = {uid})"
    ))


def downgrade() -> None:
    """Drop the claim policies. Rows already linked keep their owner."""
    for suffix in ("claim_update", "claim_select"):
        op.execute(sa.text(f"DROP POLICY IF EXISTS {_TABLE}_{suffix} ON public.{_TABLE}"))
