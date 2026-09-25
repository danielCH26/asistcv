"""Add subscriptions, payments, usage_counters, and stripe_webhook_events tables.

Revision ID: 009_subscriptions_payments
Revises: 008
Create Date: 2026-09-24

This migration adds:
- subscriptions: user subscription plans (free, job_seeker_monthly, recruiter_*)
- payments: payment history
- stripe_webhook_events: idempotency ledger for webhooks
- usage_counters: monthly usage tracking for plan limits
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "009_subscriptions_payments"
down_revision: str = "008"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    # Plan enum values
    plan_types = ("free", "job_seeker_monthly", "recruiter_starter", "recruiter_business", "recruiter_agency")
    status_types = ("active", "past_due", "canceled", "incomplete")

    # Create subscriptions table
    op.create_table(
        "subscriptions",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("plan", sa.String(50), nullable=False, server_default="free"),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("stripe_customer_id", sa.String(100), nullable=True),
        sa.Column("stripe_subscription_id", sa.String(100), nullable=True, unique=True),
        sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(f"plan IN {plan_types}", name="subscriptions_plan_check"),
        sa.CheckConstraint(f"status IN {status_types}", name="subscriptions_status_check"),
    )
    op.create_index("idx_subscriptions_user_id", "subscriptions", ["user_id"])
    op.create_index("idx_subscriptions_user_active", "subscriptions", ["user_id"], postgresql_where=sa.text("status = 'active'"))

    # Create payments table
    op.create_table(
        "payments",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("stripe_payment_intent_id", sa.String(100), nullable=True),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="usd"),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("idx_payments_user_id", "payments", ["user_id"])

    # Create stripe_webhook_events table for idempotency
    op.create_table(
        "stripe_webhook_events",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("event_id", sa.String(100), nullable=False, unique=True),
        sa.Column("type", sa.String(50), nullable=False),
        sa.Column("payload_json", postgresql.JSONB(), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_stripe_webhook_events_event_id", "stripe_webhook_events", ["event_id"])

    # Create usage_counters table for monthly usage tracking
    op.create_table(
        "usage_counters",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("matches_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("analyses_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "period_start", name="idx_usage_counter_unique"),
    )
    op.create_index("idx_usage_counters_user_period", "usage_counters", ["user_id", "period_start"])


def downgrade() -> None:
    op.drop_table("usage_counters")
    op.drop_table("stripe_webhook_events")
    op.drop_table("payments")
    op.drop_table("subscriptions")
