"""Add audit_uploads and audit_funnel_events tables.

Revision ID: 006
Revises: 005_analyses_cv_fk
Create Date: 2026-09-23
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "006"
down_revision: str = "005_analyses_cv_fk"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create audit_uploads table for anonymous CV audit storage
    op.create_table(
        "audit_uploads",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("audit_token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("cv_text", sa.Text(), nullable=True),
        sa.Column("jd_text", sa.Text(), nullable=False),
        sa.Column("pdf_blob", sa.LargeBinary(length=10485760), nullable=True),  # 10MB max
        sa.Column("audit_result_json", sa.JSON(), nullable=True),
        sa.Column("email_captured", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("linked_user_id", sa.Integer(), nullable=True),
        sa.Column("ip_hash", sa.String(64), nullable=True),
        sa.Column("user_agent", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["linked_user_id"], ["users.id"],),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_audit_expires", "audit_uploads", ["expires_at"])
    op.create_index("idx_audit_linked", "audit_uploads", ["linked_user_id"])
    op.create_index("idx_audit_token_hash", "audit_uploads", ["audit_token_hash"])

    # Create audit_funnel_events table for telemetry
    op.create_table(
        "audit_funnel_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ip_hash", sa.String(64), nullable=True),
        sa.Column("step", sa.String(50), nullable=False),
        sa.Column("audit_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["audit_id"], ["audit_uploads.id"],),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_funnel_step", "audit_funnel_events", ["step"])
    op.create_index("idx_funnel_audit_id", "audit_funnel_events", ["audit_id"])


def downgrade() -> None:
    op.drop_table("audit_funnel_events")
    op.drop_table("audit_uploads")
