"""Add FK from subscriptions.user_id to users.id.

Revision ID: 010_subscriptions_user_fk
Revises: 009
Create Date: 2026-09-24

This migration adds a foreign key constraint to ensure referential integrity
between subscriptions.user_id and users.id.
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "010_subscriptions_user_fk"
down_revision: str = "009_subscriptions_payments"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    # Add foreign key constraint from subscriptions.user_id to users.id
    op.create_foreign_key(
        "fk_subscriptions_user_id_users",
        "subscriptions",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_subscriptions_user_id_users",
        "subscriptions",
        type_="foreignkey",
    )
