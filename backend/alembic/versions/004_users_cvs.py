"""Add users_cvs table for CV management

Revision ID: 004_users_cvs
Revises: 003_users_and_refresh_tokens
Create Date: 2026-09-23

This migration adds:
- users_cvs table with PDF storage, raw text, structured JSON, and embedding
- Index on owner_user_id for fast lookups
- HNSW index on embedding for cosine similarity search
"""
from collections.abc import Sequence

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '004_users_cvs'
down_revision: str | Sequence[str] | None = '003_users_and_refresh_tokens'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Create users_cvs table
    op.create_table(
        'users_cvs',
        sa.Column('id', sa.Integer(), nullable=True),
        sa.Column('owner_user_id', sa.Integer(), nullable=False),
        sa.Column('original_filename', sa.String(length=500), nullable=False),
        sa.Column('detected_locale', sa.String(length=10), nullable=True),
        sa.Column('raw_blob', sa.LargeBinary(length=16777215), nullable=True),  # 16MB max (slightly larger than 10MB limit)
        sa.Column('raw_text', sa.Text(), nullable=True),
        sa.Column('structured', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('embedding', Vector(1024), nullable=True),  # vector(1024) for pgvector HNSW index
        sa.Column('embedding_model', sa.String(length=100), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=True),
        sa.Column('last_edited_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_cvs_id'), 'users_cvs', ['id'], unique=False)
    op.create_index(op.f('ix_users_cvs_owner_user_id'), 'users_cvs', ['owner_user_id'], unique=False)

    # Create HNSW index for vector similarity search (requires pgvector extension)
    # Note: This index is created with IF NOT EXISTS to handle cases where pgvector
    # might not be fully set up. The actual embedding storage uses bytea for now.
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_users_cvs_embedding_hnsw
        ON users_cvs USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
        WHERE embedding IS NOT NULL
    """)


def downgrade() -> None:
    # Drop HNSW index
    op.execute("DROP INDEX IF EXISTS idx_users_cvs_embedding_hnsw")

    # Drop users_cvs table
    op.drop_index(op.f('ix_users_cvs_owner_user_id'), table_name='users_cvs')
    op.drop_index(op.f('ix_users_cvs_id'), table_name='users_cvs')
    op.drop_table('users_cvs')
