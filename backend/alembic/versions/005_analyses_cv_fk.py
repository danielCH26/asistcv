"""Add FK analyses.cv_id ON DELETE SET NULL

Revision ID: 005_analyses_cv_fk
Revises: 004_users_cvs
Create Date: 2026-09-23

Adds foreign key from analyses.cv_id to users_cvs.id with ON DELETE SET NULL
to preserve orphaned analyses when a CV is deleted (R5).
"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '005_analyses_cv_fk'
down_revision: str | Sequence[str] | None = '004_users_cvs'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add cv_id column to analyses if not exists (should exist from earlier)
    # Then add FK with ON DELETE SET NULL using named constraint
    from sqlalchemy import text

    # First ensure the cv_id column exists (without FK constraint)
    op.execute(text("""
        ALTER TABLE analyses
        ADD COLUMN IF NOT EXISTS cv_id INTEGER
    """))

    # Then add the named FK constraint if it doesn't exist
    op.create_foreign_key(
        'fk_analyses_cv',
        'analyses',
        'users_cvs',
        ['cv_id'],
        ['id'],
        ondelete='SET NULL'
    )


def downgrade() -> None:
    from sqlalchemy import text

    # Drop the named FK constraint - this makes the migration reversible
    # Also drop the legacy inline FK constraint if it exists (from older migration version)
    op.drop_constraint('fk_analyses_cv', 'analyses', type_='foreignkey')
    op.execute(text("ALTER TABLE analyses DROP CONSTRAINT IF EXISTS analyses_cv_id_fkey"))
    # Note: we don't drop the cv_id column as it may contain data
