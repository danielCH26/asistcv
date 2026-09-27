"""Add ``cv_adaptations`` table for asynchronous CV-to-JD adaptation.

Revision ID: 015_cv_adaptations
Revises: 014_users_cvs_content_version
Create Date: 2026-09-27

Slice A foundation (PR1). Mirrors the table described in
``openspec/changes/sprint-adapt-cv-outreach/specs/cv-adaptation/spec.md``
(Requirement: "Modelo CVAdaptation y aislamiento RLS"). The table is
intentionally minimal in PR1 — additional operational columns
(``content_version``, ``score_estimated``, ``retry_attempts``,
``started_at``, ``failed_at``, ``jd_text``) are added in PR2.

Critical constraints
--------------------
* ``parent_cv_id`` FK to ``users_cvs.id`` ``ON DELETE SET NULL``
  (cv-management spec R2 — orphan rows kept for audit; no cascade).
* ``owner_user_id`` FK to ``users.id`` ``ON DELETE CASCADE`` (drops
  the owner's adaptations when the user is hard-deleted).
* ``status`` is ``VARCHAR(20)`` + ``CHECK`` over
  (``pending``, ``completed``, ``failed``); mirrors the Sprint 2
  ``subscriptions.status`` pattern (migration 009).
* Timestamps are ``TIMESTAMP WITH TIME ZONE`` (UTC, post-013).

Indexes (named for downgrade-by-name)
-------------------------------------
* ``idx_cv_adapt_owner_status_created`` — user history listing.
* ``idx_cv_adapt_parent_created`` — ``GET /v1/cvs/{id}/adaptations``.
* ``idx_cv_adapt_jd_hash`` — secondary lookup for cache analysis.
* ``uq_cv_adapt_parent_jd_hash_completed`` partial UNIQUE on
  ``(parent_cv_id, jd_text_hash) WHERE status='completed'`` — keeps
  concurrent POSTs idempotent.

RLS is created separately in migration 016.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "015_cv_adaptations"
down_revision: str | Sequence[str] | None = "014_users_cvs_content_version"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_STATUS_VALUES = ("pending", "completed", "failed")


def upgrade() -> None:
    """Create ``cv_adaptations`` and its indexes (RLS lands in 016)."""
    op.create_table(
        "cv_adaptations",
        sa.Column("id", sa.BigInteger(), nullable=False, autoincrement=True),
        sa.Column(
            "parent_cv_id",
            sa.BigInteger(),
            sa.ForeignKey("users_cvs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "owner_user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("jd_text_hash", sa.String(length=64), nullable=False),
        sa.Column("jd_text_encrypted", postgresql.BYTEA(), nullable=True),
        sa.Column("adapted_cv_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("error_code", sa.String(length=50), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_cv_adaptations"),
        sa.CheckConstraint(
            f"status IN {_STATUS_VALUES}",
            name="ck_cv_adaptations_status",
        ),
    )

    op.create_index(
        "idx_cv_adapt_owner_status_created",
        "cv_adaptations",
        ["owner_user_id", "status", sa.text("created_at DESC")],
        unique=False,
    )
    op.create_index(
        "idx_cv_adapt_parent_created",
        "cv_adaptations",
        ["parent_cv_id", sa.text("created_at DESC")],
        unique=False,
    )
    op.create_index(
        "idx_cv_adapt_jd_hash",
        "cv_adaptations",
        ["jd_text_hash"],
        unique=False,
    )
    # Partial UNIQUE: only one completed adaptation per (parent_cv, jd_hash).
    # Pending / failed rows are not constrained — many may exist concurrently
    # without violating uniqueness, mirroring how the cache layer treats the
    # lifecycle.
    op.create_index(
        "uq_cv_adapt_parent_jd_hash_completed",
        "cv_adaptations",
        ["parent_cv_id", "jd_text_hash"],
        unique=True,
        postgresql_where=sa.text("status = 'completed'"),
    )


def downgrade() -> None:
    """Revert in reverse order: partial unique → plain indexes → table."""
    op.drop_index(
        "uq_cv_adapt_parent_jd_hash_completed",
        table_name="cv_adaptations",
    )
    op.drop_index("idx_cv_adapt_jd_hash", table_name="cv_adaptations")
    op.drop_index(
        "idx_cv_adapt_parent_created", table_name="cv_adaptations"
    )
    op.drop_index(
        "idx_cv_adapt_owner_status_created", table_name="cv_adaptations"
    )
    op.drop_table("cv_adaptations")
