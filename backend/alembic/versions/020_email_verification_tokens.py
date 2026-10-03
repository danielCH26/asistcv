"""Add email_verification_tokens table for the C3 verify-email flow (issue #46).

Revision ID: 020_email_verification_tokens
Revises: 019_rename_adaptations_jd_text
Create Date: 2026-09-30

Why
---
The verify-email gate on billing (``billing.py:158``) was unsatisfiable:
``email_verified_at`` was never written anywhere and ``POST
/v1/auth/verify-email/confirm`` was a stub that returned 200 without
validating anything. To make the gate real we need a one-shot,
time-bound token issued at request time, persisted as a SHA256 hash, and
flipped to ``used_at = now()`` at confirm time.

A new table (rather than new columns on ``users``) follows the same
shape as ``refresh_tokens`` and ``audit_tokens``: keeps the hot row small
and lets the cleanup cron drop expired tokens without rewriting ``users``.

Schema
------
* ``token_hash`` is unique so two concurrent requests for the same user
  produce different tokens (we generate ``secrets.token_urlsafe(32)``
  then SHA256 it) and the lookup at confirm-time is O(1).
* ``user_id`` cascades on delete: deleting a user purges their pending
  tokens (defense in depth; nobody should ever confirm one).
* ``used_at`` is NULL until the confirm endpoint validates the token;
  the confirm endpoint refuses anything where ``used_at IS NOT NULL``
  even if the row is still inside its TTL (replay protection).
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "020_email_verification_tokens"
down_revision: str | Sequence[str] | None = "019_rename_adaptations_jd_text"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "email_verification_tokens",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("token_hash", sa.String(128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_email_verification_tokens_hash"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE"
        ),
    )
    op.create_index(
        "ix_email_verification_tokens_user_id",
        "email_verification_tokens",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_email_verification_tokens_user_id", table_name="email_verification_tokens")
    op.drop_table("email_verification_tokens")
