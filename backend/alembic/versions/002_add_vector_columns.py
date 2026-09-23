"""Columnas de vectores, índices HNSW y FK analyses.profile_id

Revision ID: 002_add_vector_columns
Revises: 001_initial_tables
Create Date: 2026-09-23

Migración 100% aditiva: agrega columnas de embedding (1024 dims), el
identificador del modelo de embeddings e índices HNSW (coseno) en las
tres tablas core, más la FK faltante analyses.profile_id. No toca datos
existentes, por lo que el downgrade es un drop simple de columnas e
índices en orden inverso.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '002_add_vector_columns'
down_revision: str | None = '001_initial_tables'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Tablas que reciben columnas de embedding + índice HNSW.
VECTOR_TABLES = ('job_descriptions', 'analyses', 'profiles')


def upgrade() -> None:
    # 1. Columnas de vector + modelo (NULLable: filas legacy quedan sin vector).
    for table in VECTOR_TABLES:
        op.add_column(table, sa.Column('embedding', Vector(1024), nullable=True))
        op.add_column(
            table, sa.Column('embedding_model', sa.String(length=100), nullable=True)
        )

    # 2. FK faltante: analyses.profile_id -> profiles.id (NULLable: las filas
    # previas conservan solo el profile_snapshot JSON).
    op.add_column('analyses', sa.Column('profile_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'fk_analyses_profile_id', 'analyses', 'profiles', ['profile_id'], ['id']
    )

    # 3. Índices HNSW para similitud coseno (operator class por defecto de pgvector).
    op.create_index(
        'idx_jd_embedding_hnsw',
        'job_descriptions',
        ['embedding'],
        postgresql_using='hnsw',
        postgresql_ops={'embedding': 'vector_cosine_ops'},
    )
    op.create_index(
        'idx_analyses_embedding_hnsw',
        'analyses',
        ['embedding'],
        postgresql_using='hnsw',
        postgresql_ops={'embedding': 'vector_cosine_ops'},
    )
    op.create_index(
        'idx_profiles_embedding_hnsw',
        'profiles',
        ['embedding'],
        postgresql_using='hnsw',
        postgresql_ops={'embedding': 'vector_cosine_ops'},
    )


def downgrade() -> None:
    # Orden inverso: primero índices, luego FK y columnas.
    op.drop_index('idx_jd_embedding_hnsw', table_name='job_descriptions')
    op.drop_index('idx_analyses_embedding_hnsw', table_name='analyses')
    op.drop_index('idx_profiles_embedding_hnsw', table_name='profiles')

    op.drop_constraint('fk_analyses_profile_id', 'analyses', type_='foreignkey')
    op.drop_column('analyses', 'profile_id')

    for table in VECTOR_TABLES:
        op.drop_column(table, 'embedding_model')
        op.drop_column(table, 'embedding')
