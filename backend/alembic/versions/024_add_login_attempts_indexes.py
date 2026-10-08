"""Add indexes on auth_login_attempts (email, attempted_at) and (ip, attempted_at).

A3 fix: The auth_login_attempts table was queried by email and attempted_at
but had no index, causing a sequential scan on every login.  A4 also added
an IP dimension to the rate limit, so we index both columns.

Indexes:
- idx_auth_login_attempts_email_attempted: for per-account rate limiting.
- idx_auth_login_attempts_ip_attempted: for per-IP rate limiting (A4).

Downgrade: drops both indexes.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "024_add_login_attempts_indexes"
down_revision: str = "023_enable_rls_profiles"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "idx_auth_login_attempts_email_attempted",
        "auth_login_attempts",
        ["email", "attempted_at"],
        unique=False,
    )
    op.create_index(
        "idx_auth_login_attempts_ip_attempted",
        "auth_login_attempts",
        ["ip", "attempted_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_auth_login_attempts_ip_attempted", table_name="auth_login_attempts")
    op.drop_index("idx_auth_login_attempts_email_attempted", table_name="auth_login_attempts")
