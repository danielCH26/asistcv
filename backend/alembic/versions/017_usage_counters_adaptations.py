"""Add ``adaptations_used`` to ``usage_counters`` for monthly billing cap.

Revision ID: 017_usage_counters_adaptations
Revises: 016_rls_cv_adaptations
Create Date: 2026-09-27

NOTE: the originally proposed slug
``017_usage_counters_adaptations_used.py`` (38 chars) bumped into the
VARCHAR(32) ceiling of ``alembic_version.version_num`` declared in
migration 001 — Postgres raised ``value too long for type character
varying(32)`` on the UPDATE that stamps the new revision. The shorter
slug kept the table-level intent (``adaptations_used`` is what lands
on the table) without touching the historical schema.

Mirrors ``openspec/changes/sprint-adapt-cv-outreach/specs/adaptation-billing/spec.md``
(Requirement: "Conteo vía usage_counters").

Behavior
--------
* ``adaptations_used INT NOT NULL DEFAULT 0`` — third resource column
  on the existing counter table. Coexists with ``matches_used`` and
  ``analyses_used`` (migration 009). None share a foreign key; they
  share ``(user_id, period_start)`` as composite identity.
* Default 0 keeps the existing-records contract: every user row
  retroactively counts as zero adaptations in the current period.
* The existing monthly rollover (Sprint 2) handles reset on
  ``current_period_start`` — no new index or check needed.

Reversibility
-------------
``downgrade()`` drops the column. Loss is limited to in-flight counters
which the recurring billing cycle would regenerate on next period.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "017_usage_counters_adaptations"
down_revision: str | Sequence[str] | None = "016_rls_cv_adaptations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add nullable=False column with server-side default for legacy rows."""
    op.add_column(
        "usage_counters",
        sa.Column(
            "adaptations_used",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    """Drop the column; downgrade-by-name not required (single column)."""
    op.drop_column("usage_counters", "adaptations_used")
