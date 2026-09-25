"""Convert all Sprint 2 timestamps to TIMESTAMP WITH TIME ZONE (UTC).

Revision ID: 013_tz_aware_timestamps
Revises: 012_audit_jd_optional
Create Date: 2026-09-25

Context
-------
Service code writes timestamps with ``datetime.now(UTC)`` (tz-aware).
asyncpg via SQLAlchemy refuses to bind a tz-aware ``datetime`` into a
``TIMESTAMP WITHOUT TIME ZONE`` column, raising::

    TypeError: can't subtract offset-naive and offset-aware datetimes

Earlier migrations (001-012) declared columns with ``DateTime(timezone=True)``
but the prod schema was created before that change took effect, so several
``TIMESTAMP WITHOUT TIME ZONE`` columns survived in the live database. The
first symptom is the 500 on ``POST /v1/auth/register`` (no refresh-token
row is written because the INSERT fails after the user row is committed —
leaving an orphan user).

This migration idempotently converts every Sprint 2 timestamp column to
``TIMESTAMP WITH TIME ZONE`` interpreting existing naive values as UTC
(the convention the service has used since day one). It is a no-op on a
freshly migrated DB where the columns are already ``timestamptz``.

Reversibility
-------------
Downgrade casts each ``timestamptz`` back to ``timestamp`` (dropping the
offset; existing values are left as their UTC wall-clock representation).
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.engine import Connection
from sqlalchemy.engine.mock import MockConnection

revision: str = "013_tz_aware_timestamps"
down_revision: str | Sequence[str] | None = "012_audit_jd_optional"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# (table, column) pairs to convert. Order is stable for readability; the
# conversion is column-independent so any order works.
_TZ_COLUMNS: list[tuple[str, str]] = [
    # --- Sprint 1 / legacy ---
    ("profiles", "created_at"),
    ("profiles", "updated_at"),
    ("job_descriptions", "created_at"),
    ("analyses", "created_at"),
    # --- Sprint 2: auth (PR1) ---
    ("users", "email_verified_at"),
    ("users", "email_verification_expires_at"),
    ("users", "last_login_at"),
    ("users", "created_at"),
    ("users", "updated_at"),
    ("users_refresh_tokens", "consumed_at"),
    ("users_refresh_tokens", "revoked_at"),
    ("users_refresh_tokens", "expires_at"),
    ("users_refresh_tokens", "created_at"),
    ("token_revocation", "exp"),
    ("token_revocation", "revoked_at"),
    ("auth_login_attempts", "attempted_at"),
    ("auth_security_events", "created_at"),
    # --- Sprint 2: CV management (PR2) ---
    ("users_cvs", "created_at"),
    ("users_cvs", "last_edited_at"),
    # --- Sprint 2: free audit (PR3) ---
    ("audit_uploads", "created_at"),
    ("audit_uploads", "expires_at"),
    ("audit_funnel_events", "created_at"),
    # --- Sprint 2: recruiter roster (PR4) ---
    ("recruiter_consents", "accepted_at"),
    ("recruiter_consents", "created_at"),
    ("recruiter_candidates_cvs", "created_at"),
    ("recruiter_candidates", "last_analysed_at"),
    ("recruiter_candidates", "created_at"),
    ("recruiter_candidates", "updated_at"),
    ("recruiter_analyses", "created_at"),
    ("recruiter_audit_log", "created_at"),
    # --- Sprint 2: billing (PR5) ---
    ("subscriptions", "current_period_start"),
    ("subscriptions", "current_period_end"),
    ("subscriptions", "created_at"),
    ("subscriptions", "updated_at"),
    ("payments", "created_at"),
    ("usage_counters", "period_start"),
    ("usage_counters", "created_at"),
    ("usage_counters", "updated_at"),
    ("stripe_webhook_events", "processed_at"),
    ("stripe_webhook_events", "created_at"),
]


def _is_naive(conn: Connection, table: str, column: str) -> bool:
    """Return True when ``table.column`` is currently ``timestamp without time zone``.

    Idempotency guard: we only ALTER columns that are still naive. On a
    freshly migrated DB this returns False for every column and the
    migration is a no-op.
    """
    row = conn.execute(
        sa.text(
            """
            SELECT data_type FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = :t
              AND column_name = :c
            """
        ),
        {"t": table, "c": column},
    ).fetchone()
    if row is None:
        return False
    return row[0] == "timestamp without time zone"


def _is_tz(conn: Connection, table: str, column: str) -> bool:
    """Inverse of ``_is_naive`` used by the downgrade path."""
    row = conn.execute(
        sa.text(
            """
            SELECT data_type FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = :t
              AND column_name = :c
            """
        ),
        {"t": table, "c": column},
    ).fetchone()
    if row is None:
        return False
    return row[0] == "timestamp with time zone"


def _is_live(conn: object | None) -> bool:
    """``True`` when we have a real DB connection (online / non-mock)."""
    return conn is not None and not isinstance(conn, MockConnection)


def upgrade() -> None:
    """Convert each naive ``timestamp`` column to ``timestamptz`` (UTC).

    ``USING ... AT TIME ZONE 'UTC'`` tells Postgres: treat the existing
    naive value as a UTC wall-clock and attach the UTC offset. The result
    is a ``timestamptz`` whose instant equals the original UTC moment.

    In offline / mock mode (``--sql``) we have no live introspection so
    every ALTER is emitted unconditionally; the runtime guard makes the
    online apply idempotent.
    """
    conn = op.get_bind()
    live = _is_live(conn)
    for table, column in _TZ_COLUMNS:
        if live and not _is_naive(conn, table, column):
            continue
        op.execute(
            sa.text(
                f"ALTER TABLE {table} ALTER COLUMN {column} "
                f"TYPE TIMESTAMP WITH TIME ZONE USING {column} AT TIME ZONE 'UTC'"
            )
        )


def downgrade() -> None:
    """Revert each ``timestamptz`` column back to naive ``timestamp``.

    The ``AT TIME ZONE 'UTC'`` cast drops the offset and keeps the
    UTC wall-clock value, matching the convention the service code used
    before this migration.
    """
    conn = op.get_bind()
    live = _is_live(conn)
    for table, column in _TZ_COLUMNS:
        if live and not _is_tz(conn, table, column):
            continue
        op.execute(
            sa.text(
                f"ALTER TABLE {table} ALTER COLUMN {column} "
                f"TYPE TIMESTAMP WITHOUT TIME ZONE USING {column} AT TIME ZONE 'UTC'"
            )
        )