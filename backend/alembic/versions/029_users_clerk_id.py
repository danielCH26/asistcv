"""
029_users_clerk_id: add clerk_id column and make password_hash nullable.

Migration S1 of feat/clerk-auth-migration.

- ALTER TABLE users ADD COLUMN clerk_id VARCHAR(64) NULL + unique index.
  Nullable so legacy users (without Clerk) keep clerk_id=NULL. Clerk-provisioned
  users always have a clerk_id from Clerk (globally unique there). Multiple
  NULLs are allowed by a Postgres unique index, so legacy rows coexist.
- ALTER COLUMN password_hash DROP NOT NULL (Clerk users have no password).

Downgrade: reverse all three operations (index, NOT NULL, column).
"""

from collections.abc import Sequence

from alembic import op

revision: str = "029_users_clerk_id"
down_revision: str = "028_payment_methods"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

_TABLE = "users"


def upgrade() -> None:
    # Add clerk_id column as nullable (NULL for legacy users, non-NULL for Clerk).
    op.execute(f"ALTER TABLE {_TABLE} ADD COLUMN clerk_id VARCHAR(64)")
    # DB-level uniqueness for clerk_id (mirrors User.clerk_id unique=True;
    # concurrent provisioning races then fail with IntegrityError and the
    # dependency re-selects instead of double-inserting).
    op.execute(
        f"CREATE UNIQUE INDEX ix_users_clerk_id ON {_TABLE} (clerk_id)"
    )
    # Make password_hash nullable (Clerk-provisioned users have no password).
    op.execute(f"ALTER TABLE {_TABLE} ALTER COLUMN password_hash DROP NOT NULL")


def downgrade() -> None:
    # Re-add NOT NULL to password_hash (fails if Clerk users with NULL exist;
    # reversible-cycle correctness on a pristine DB is what CI checks).
    op.execute(f"ALTER TABLE {_TABLE} ALTER COLUMN password_hash SET NOT NULL")
    op.execute("DROP INDEX IF EXISTS ix_users_clerk_id")
    # Drop the clerk_id column.
    op.execute(f"ALTER TABLE {_TABLE} DROP COLUMN clerk_id")
