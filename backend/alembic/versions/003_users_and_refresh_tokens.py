"""Add users, refresh tokens, and auth support tables

Revision ID: 003_users_and_refresh_tokens
Revises: 002_add_vector_columns
Create Date: 2026-09-23

This migration adds:
- users table with role CHECK constraint
- users_refresh_tokens table for JWT refresh
- token_revocation for access token blacklist
- auth_login_attempts for brute-force protection
- auth_security_events for security logging
- Adds owner_user_id to profiles and analyses tables
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '003_users_and_refresh_tokens'
down_revision: str | Sequence[str] | None = '002_add_vector_columns'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Enable citext extension for case-insensitive email
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")

    # Create users table
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), nullable=True),
        sa.Column('email', postgresql.CITEXT(), nullable=False, unique=True),
        sa.Column('password_hash', sa.Text(), nullable=False),
        sa.Column('role', sa.String(length=20), nullable=False),
        sa.Column('full_name', sa.String(length=255), nullable=False),
        sa.Column('locale', sa.String(length=10), nullable=False, server_default='es'),
        sa.Column('avatar_url', sa.Text(), nullable=True),
        sa.Column('email_verified_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('email_verification_token_hash', sa.Text(), nullable=True),
        sa.Column('email_verification_expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint("role IN ('job_seeker', 'recruiter')", name='users_role_check')
    )
    op.create_index(op.f('ix_users_id'), 'users', ['id'], unique=False)
    op.create_index(op.f('ix_users_role'), 'users', ['role'], unique=False)

    # Create users_refresh_tokens table
    op.create_table(
        'users_refresh_tokens',
        sa.Column('id', sa.Integer(), nullable=True),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('token_hash', sa.Text(), nullable=False, unique=True),
        sa.Column('consumed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=True),
        sa.Column('user_agent', sa.Text(), nullable=True),
        sa.Column('ip', sa.String(length=45), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_refresh_tokens_id'), 'users_refresh_tokens', ['id'], unique=False)
    # Partial index for active tokens
    op.execute("""
        CREATE INDEX idx_refresh_user_active
        ON users_refresh_tokens(user_id)
        WHERE consumed_at IS NULL AND revoked_at IS NULL
    """)

    # Create token_revocation table (for access token blacklist)
    op.create_table(
        'token_revocation',
        sa.Column('id', sa.Integer(), nullable=True),
        sa.Column('jti', sa.String(length=64), nullable=False, unique=True),
        sa.Column('exp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('revoked_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_token_revocation_id'), 'token_revocation', ['id'], unique=False)

    # Create auth_login_attempts table
    op.create_table(
        'auth_login_attempts',
        sa.Column('id', sa.Integer(), nullable=True),
        sa.Column('email', postgresql.CITEXT(), nullable=False),
        sa.Column('ip', sa.String(length=45), nullable=True),
        sa.Column('success', sa.Boolean(), nullable=False),
        sa.Column('attempted_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_auth_login_attempts_id'), 'auth_login_attempts', ['id'], unique=False)

    # Create auth_security_events table
    op.create_table(
        'auth_security_events',
        sa.Column('id', sa.Integer(), nullable=True),
        sa.Column('event', sa.String(length=50), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('ip', sa.String(length=45), nullable=True),
        sa.Column('user_agent', sa.Text(), nullable=True),
        sa.Column('details', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_auth_security_events_id'), 'auth_security_events', ['id'], unique=False)

    # Add owner_user_id to profiles (for user-bound history)
    op.add_column('profiles', sa.Column('owner_user_id', sa.Integer(), nullable=True))
    op.create_index(op.f('ix_profiles_owner_user_id'), 'profiles', ['owner_user_id'], unique=False)
    op.create_foreign_key(
        'fk_profiles_owner_user_id_users',
        'profiles', 'users',
        ['owner_user_id'], ['id'],
        ondelete='SET NULL'
    )

    # Add owner_user_id to analyses (for user-bound history)
    op.add_column('analyses', sa.Column('owner_user_id', sa.Integer(), nullable=True))
    op.create_index(op.f('ix_analyses_owner_user_id'), 'analyses', ['owner_user_id'], unique=False)
    op.create_foreign_key(
        'fk_analyses_owner_user_id_users',
        'analyses', 'users',
        ['owner_user_id'], ['id'],
        ondelete='SET NULL'
    )


def downgrade() -> None:
    # Remove owner_user_id from analyses
    op.drop_constraint('fk_analyses_owner_user_id_users', 'analyses', type_='foreignkey')
    op.drop_index(op.f('ix_analyses_owner_user_id'), table_name='analyses')
    op.drop_column('analyses', 'owner_user_id')

    # Remove owner_user_id from profiles
    op.drop_constraint('fk_profiles_owner_user_id_users', 'profiles', type_='foreignkey')
    op.drop_index(op.f('ix_profiles_owner_user_id'), table_name='profiles')
    op.drop_column('profiles', 'owner_user_id')

    # Drop auth_security_events
    op.drop_index(op.f('ix_auth_security_events_id'), table_name='auth_security_events')
    op.drop_table('auth_security_events')

    # Drop auth_login_attempts
    op.drop_index(op.f('ix_auth_login_attempts_id'), table_name='auth_login_attempts')
    op.drop_table('auth_login_attempts')

    # Drop token_revocation
    op.drop_index(op.f('ix_token_revocation_id'), table_name='token_revocation')
    op.drop_table('token_revocation')

    # Drop users_refresh_tokens
    op.execute("DROP INDEX IF EXISTS idx_refresh_user_active")
    op.drop_index(op.f('ix_users_refresh_tokens_id'), table_name='users_refresh_tokens')
    op.drop_table('users_refresh_tokens')

    # Drop users
    op.drop_index(op.f('ix_users_role'), table_name='users')
    op.drop_index(op.f('ix_users_id'), table_name='users')
    op.drop_table('users')

    # Note: We don't drop citext extension as other tables might use it
