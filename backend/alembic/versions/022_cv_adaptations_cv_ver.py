"""Snapshot ``users_cvs.content_version`` onto every ``cv_adaptations`` row.

Revision ID: 022_cv_adaptations_cv_ver
Revises: 021_cv_adaptations_pending_uq
Create Date: 2026-10-06

Why
---
Slice A's design D2 promised the cache key ``(parent_cv_id,
content_version, jd_text_hash)`` would invalidate cached adaptations when
the source CV is edited (``PATCH /v1/cvs/{id}`` bumps ``content_version``
in the same transaction as the structured-data update, migration 014).
The column was never created on ``cv_adaptations``: every cached row
was written without a snapshot, and ``app.services.adaptation_cache``
fell back to a "defensive check" that compared the source CV's CURRENT
``content_version`` against the value supplied by the caller — which had
read the same ``users_cvs.content_version`` in the same request, so the
comparison was ``x == x`` and the check never satisfied. After editing a
CV, a repeat ``POST /v1/adaptations`` inside the 24 h cache window
returned the adaptation generated against the pre-edit CV. A green
test in ``test_adaptation_cache.py`` was actively concealing this by
deliberately mismatching the value (line 251: ``content_version=2``
against a fixture at ``1``), which exercised the wrong invariant.

This migration closes the gap by snapshotting the source CV's
``content_version`` onto the adaptation row at write time. The cache
lookup then compares the row's snapshot to the CV's current value:
match means the source CV has not been edited since the row was
written, miss means it has been, and the runner rebuilds against the
new CV.

Behavior
--------
- ``content_version INT NOT NULL DEFAULT 1`` on ``cv_adaptations`` —
  every row existing before this migration defaults to 1, matching
  the seed value for ``users_cvs.content_version`` (migration 014),
  so pre-existing rows keep their original (pre-edit) interpretation.
- No new index. The cache lookup is already served by the covering
  index ``uq_cv_adapt_parent_jd_hash_pending`` on
  ``(parent_cv_id, jd_text_hash)`` scoped to ``status='pending'``;
  the completed-row read uses the same pair (migration 021 left that
  shape unchanged), so adding ``content_version`` to the key does not
  need its own index.
- The partial unique index from migration 021
  (``uq_cv_adapt_parent_jd_hash_pending``) is left in place: it
  guards the in-flight invariant (``at most one pending row per
  (cv, jd)``), which has nothing to do with the snapshot.

Reversibility
-------------
``downgrade()`` drops the column. No data loss: a re-run of the
endpoint will re-write the snapshot from the source CV at write time.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "022_cv_adaptations_cv_ver"
down_revision: str | Sequence[str] | None = "021_cv_adaptations_pending_uq"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Snapshot ``users_cvs.content_version`` onto ``cv_adaptations``.

    ``server_default='1'`` is the source of truth for legacy rows:
    ``users_cvs.content_version`` was seeded to 1 in migration 014, so
    a default of 1 here keeps pre-existing adaptations consistent with
    the CV they were derived from at the time this migration ran.
    """
    op.add_column(
        "cv_adaptations",
        sa.Column(
            "content_version",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
    )


def downgrade() -> None:
    """Drop the snapshot column; no data loss (re-stamped on next write)."""
    op.drop_column("cv_adaptations", "content_version")