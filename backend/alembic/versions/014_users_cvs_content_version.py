"""Add ``content_version`` to ``users_cvs`` for cache invalidation.

Revision ID: 014_users_cvs_content_version
Revises: 013_tz_aware_timestamps
Create Date: 2026-09-27

Slice A foundation (PR1). The new column tracks how many times a CV
has been edited via ``PATCH /v1/cvs/{id}``. Slice A reads it from the
adaptation cache layer (PR2) so a CV edit auto-invalidates cached
adaptations whose key includes ``content_version`` (design D2).

Behavior
--------
- ``content_version INT NOT NULL DEFAULT 1`` — every row existing
  before this migration defaults to 1 (one fresh version).
- Bump site: ``PATCH /v1/cvs/{id}`` increments by 1 in the same DB
  transaction as the structured-data update.

Reversibility
-------------
``downgrade()`` drops the column. No data loss because the column is
cheap to recompute on next PATCH (or set back to 1 for legacy rows).
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "014_users_cvs_content_version"
down_revision: str | Sequence[str] | None = "013_tz_aware_timestamps"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add nullable=False column with server-side default for legacy rows."""
    op.add_column(
        "users_cvs",
        sa.Column(
            "content_version",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
    )


def downgrade() -> None:
    """Drop the column; downgrade-by-name not required (single column)."""
    op.drop_column("users_cvs", "content_version")
