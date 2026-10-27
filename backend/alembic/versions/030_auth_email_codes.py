"""
030_auth_email_codes: table for passwordless email-code login codes.

Slice S1a of feat/passwordless-auth (Clerk replacement).

- CREATE TABLE auth_email_codes: one row per issued code. The plaintext
  6-digit code only ever lives in the email; the table stores its SHA256
  hex digest (same secret-storage pattern as refresh tokens and email
  verification tokens).
- email is indexed for the "latest live code per email" lookup; code_hash
  is unique because verification matches by hash first.
- attempts counts failed verifications so verify can enforce
  settings.email_code_max_attempts without a separate table.

Downgrade: DROP TABLE.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "030_auth_email_codes"
down_revision: str = "029_users_clerk_id"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

_TABLE = "auth_email_codes"


def upgrade() -> None:
    op.execute(
        f"""CREATE TABLE {_TABLE} (
            id SERIAL PRIMARY KEY,
            email VARCHAR(320) NOT NULL,
            code_hash VARCHAR(128) NOT NULL,
            purpose VARCHAR(32) NOT NULL DEFAULT 'login',
            attempts INTEGER NOT NULL DEFAULT 0,
            expires_at TIMESTAMPTZ NOT NULL,
            used_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )"""
    )
    op.execute(
        f"CREATE INDEX ix_auth_email_codes_email ON {_TABLE} (email)"
    )
    op.execute(
        f"CREATE UNIQUE INDEX ix_auth_email_codes_code_hash ON {_TABLE} (code_hash)"
    )


def downgrade() -> None:
    op.execute(f"DROP TABLE {_TABLE}")
