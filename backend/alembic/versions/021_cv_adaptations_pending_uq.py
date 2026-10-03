"""Scope the ``cv_adaptations`` uniqueness to IN-FLIGHT rows, not completed ones.

Revision ID: 021_cv_adaptations_pending_uq
Revises: 020_email_verification_tokens
Create Date: 2026-10-03

Why
---
Migration 015 created::

    UNIQUE (parent_cv_id, jd_text_hash) WHERE status = 'completed'

The intent was "concurrent POSTs are idempotent". The effect was "a
(cv, jd) pair may be completed exactly once in the table's entire
lifetime", which is a different and much stronger claim than the system
is designed around. It breaks in two ways, and both discard an LLM call
that has already been paid for:

1. **Cache TTL vs sweeper window.** The cache serves a completed row for
   24 h (``adaptation_cache.CACHE_TTL``) but the sweeper only deletes
   completed rows after 90 days (``COMPLETED_RETENTION_DAYS``). A repeat
   request at T+25h misses the cache, inserts a fresh ``pending`` row,
   the runner does the work, and the final ``UPDATE`` to ``completed``
   violates this index. The ``IntegrityError`` is swallowed by the
   runner's caller, so the row stays ``pending``.
2. **CV edits.** The cache key is ``(parent_cv_id, content_version,
   jd_text_hash)`` — an edit to the CV bumps ``content_version`` and
   deliberately forces a miss — but the index has no
   ``content_version``, so re-adapting the same JD after an edit
   collides immediately, with no TTL involved at all.

What the invariant should be
---------------------------
The expensive, irreversible resource is the LLM call. So the constraint
worth enforcing is the one that STOPS wasted work, and the constraint
that must not exist is the one that BLOCKS a legitimate rerun:

* At most one **pending** adaptation per ``(cv, jd)`` — this is the
  real anti-concurrency invariant. Two in-flight runners for the same
  input mean the user is charged once and we pay twice. The new index
  makes that a database guarantee instead of a race-dependent
  application check.
* Completed rows become append-only history. Adapting the same JD twice
  months apart is a legitimate thing for a user to do, and
  ``GET /v1/adaptations/by-cv/{cv_id}`` is a history listing.

After this change the three windows stop fighting each other and each
owns exactly one concern: the 24 h TTL decides what a user is *shown*,
the 90-day sweeper decides how long history is *retained*, and this
index decides only *concurrency*. Neither window is modified.

Pre-flight data fix
-------------------
Because the old index did not constrain ``pending`` rows, duplicates
may already exist (a concurrent pair of POSTs creates exactly that). A
plain ``CREATE UNIQUE INDEX`` would abort on them, so they are collapsed
first: every pending row that has an earlier pending sibling for the same
``(parent_cv_id, jd_text_hash)`` is moved to ``failed`` with
``DUPLICATE_SUPERSEDED``. The oldest row wins, so the job that started
first is the one that survives, and no client is left polling a row that
vanished. Failed rows are not covered by the new index, so a runner that
finishes a superseded row afterwards still lands in ``completed``
without conflict.

The DML runs under the service GUC (``SET LOCAL app.current_user_id =
'0'``) rather than relying on the migration role being a superuser:
``cv_adaptations`` has FORCE ROW LEVEL SECURITY (migration 016), which
applies to the table owner too, so an unprivileged owner would otherwise
update zero rows and the unique index would still fail to build.

``parent_cv_id`` is matched with ``=`` and not ``IS NOT DISTINCT FROM``:
the column is nullable and btree treats NULLs as distinct, so orphan
rows (``ON DELETE SET NULL``) were never constrained by the old index
and must not start conflicting now.

Scope
-----
Index-only DDL plus the one idempotent UPDATE above. No column is added,
no table is rewritten, and no LLM-relevant state is destroyed. Ordinary
(non-CONCURRENTLY) DDL is used so that ``upgrade()``/``downgrade()`` stay
atomic and symmetric inside alembic's transaction; the table is bounded
by the sweeper, so the brief lock is not worth trading that away. If it
ever grows large enough to matter, switch both statements to
``CONCURRENTLY`` inside ``op.get_bind().execution_options(autocommit_block())``.

Reversibility
-------------
``downgrade()`` recreates the completed-scoped index. It can fail if two
completed rows for the same ``(parent_cv_id, jd_text_hash)`` exist at
that point, which is exactly the state this migration makes legal — the
downgrade is a return to the old, narrower invariant, not a loss of
data.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "021_cv_adaptations_pending_uq"
down_revision: str | Sequence[str] | None = "020_email_verification_tokens"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "cv_adaptations"
_OLD_INDEX = "uq_cv_adapt_parent_jd_hash_completed"
_NEW_INDEX = "uq_cv_adapt_parent_jd_hash_pending"

# The old index is dropped first: while it still exists, a re-run of a
# completed (cv, jd) pair would violate IT rather than the new one, so
# the order matters for an idempotent re-apply.
_DROP_OLD = f"DROP INDEX IF EXISTS {_OLD_INDEX}"
_CREATE_OLD = (
    f"CREATE UNIQUE INDEX {_OLD_INDEX} ON {_TABLE} "
    "(parent_cv_id, jd_text_hash) WHERE status = 'completed'"
)
_CREATE_NEW = (
    f"CREATE UNIQUE INDEX {_NEW_INDEX} ON {_TABLE} "
    "(parent_cv_id, jd_text_hash) WHERE status = 'pending'"
)

_COLLAPSE_DUPLICATE_PENDING = f"""
UPDATE {_TABLE} AS a
   SET status = 'failed',
       error_code = 'DUPLICATE_SUPERSEDED',
       error_message = 'Superseded by an earlier in-flight adaptation '
                       'for the same CV and JD.',
       completed_at = NOW()
 WHERE a.status = 'pending'
   AND EXISTS (
       SELECT 1
         FROM {_TABLE} AS b
        WHERE b.status = 'pending'
          AND b.parent_cv_id = a.parent_cv_id
          AND b.jd_text_hash = a.jd_text_hash
          AND b.id < a.id
   )
"""

# Service bypass (migration 016): the cron context, id '0'. Bound with
# SET LOCAL because migration DDL/DML runs in a transaction.
_BIND_SERVICE = "SET LOCAL app.current_user_id = '0'"


def upgrade() -> None:
    """Replace the completed-scoped index with a pending-scoped one."""
    op.execute(sa.text(_DROP_OLD))
    op.execute(sa.text(_BIND_SERVICE))
    op.execute(sa.text(_COLLAPSE_DUPLICATE_PENDING))
    op.execute(sa.text(_CREATE_NEW))


def downgrade() -> None:
    """Restore the completed-scoped index (see the reversibility note)."""
    op.execute(sa.text(f"DROP INDEX IF EXISTS {_NEW_INDEX}"))
    op.execute(sa.text(_BIND_SERVICE))
    op.execute(sa.text(_CREATE_OLD))
