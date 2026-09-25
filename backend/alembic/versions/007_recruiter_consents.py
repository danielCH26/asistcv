"""
Add recruiter_consents table for ToS consent tracking.

This migration creates the recruiter_consents table to track when recruiters
accept the Terms of Service and good faith declaration. This is required
for the consent gate on recruiter endpoints (PR4).

Revision ID: 007
Revises: 006
Create Date: 2024-01-15
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "007"
down_revision: str = "006"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    # Create recruiter_consents table
    op.create_table(
        "recruiter_consents",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tos_version", sa.String(50), nullable=False),
        sa.Column("ip", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    # Add unique constraint - one consent per user
    op.create_index(
        "idx_recruiter_consents_user_id",
        "recruiter_consents",
        ["user_id"],
        unique=True,
    )

    # Add foreign key to users
    op.create_foreign_key(
        "fk_recruiter_consents_user_id",
        "recruiter_consents",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint("fk_recruiter_consents_user_id", "recruiter_consents", type_="foreignkey")
    op.drop_index("idx_recruiter_consents_user_id", table_name="recruiter_consents")
    op.drop_table("recruiter_consents")
