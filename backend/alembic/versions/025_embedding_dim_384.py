"""Cambiar embedding de vector(1024) a vector(384) en 4 tablas.

Issue #101 / T1 (local embeddings): el nuevo provider local
(``paraphrase-multilingual-MiniLM-L12-v2``) produce vectores de 384
dimensiones, incompatible con las columnas existentes de 1024 dims.

Upgrade:
  1. Dropea los índices HNSW (dimensionados en 1024).
  2. SET embedding = NULL en las 4 tablas (vectores de 1024 no son
     convertibles a 384 — match.py re-embeddea on-demand).
  3. ALTER TYPE a vector(384) con USING embedding::text::vector.
  4. Recrear índices HNSW con la nueva dimensión.

Downgrade:
  1. Dropea los índices HNSW (dimensionados en 384).
  2. ALTER TYPE de vuelta a vector(1024) con NULLs
     (data loss: los vectores de 384 no se convierten a 1024).
  3. Recrear índices HNSW con dimensión 1024.

users_cvs NO tiene índice HNSW (migración 004 no lo creó).
"""

from collections.abc import Sequence

from alembic import op

revision: str = "025_embedding_dim_384"
down_revision: str = "024_add_login_attempts_indexes"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

# Tablas con columna embedding que reciben el ALTER TYPE.
VECTOR_TABLES = ("profiles", "job_descriptions", "analyses", "users_cvs")

# Tablas con índice HNSW sobre embedding (creado en migración 002).
# users_cvs NO tiene índice HNSW.
HNSW_TABLES = ("profiles", "job_descriptions", "analyses")

# Índices HNSW existentes sobre embedding (migración 002).
HNSW_INDEXES = (
    ("idx_profiles_embedding_hnsw", "profiles"),
    ("idx_jd_embedding_hnsw", "job_descriptions"),
    ("idx_analyses_embedding_hnsw", "analyses"),
)


def upgrade() -> None:
    # 1. Dropear índices HNSW (dimensionados para 1024) antes del ALTER TYPE.
    for index_name, table_name in HNSW_INDEXES:
        op.drop_index(index_name, table_name=table_name)

    # 2. Nullear vectores existentes (1024) — no son convertibles a 384.
    for table in VECTOR_TABLES:
        op.execute(f"UPDATE {table} SET embedding = NULL WHERE embedding IS NOT NULL")

    # 3. ALTER TYPE vector(1024) → vector(384) con cast ::text::vector.
    for table in VECTOR_TABLES:
        op.execute(
            f"ALTER TABLE {table} "
            f"ALTER COLUMN embedding TYPE vector(384) "
            f"USING embedding::text::vector"
        )

    # 4. Recrear índices HNSW con la nueva dimensión 384.
    for index_name, table_name in HNSW_INDEXES:
        op.create_index(
            index_name,
            table_name,
            ["embedding"],
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        )


def downgrade() -> None:
    # 1. Dropear índices HNSW (dimensionados para 384).
    for index_name, table_name in HNSW_INDEXES:
        op.drop_index(index_name, table_name=table_name)

    # 2. ALTER TYPE vector(384) → vector(1024) con NULLs.
    #    Data loss: los vectores de 384 dims no se convierten a 1024.
    for table in VECTOR_TABLES:
        op.execute(f"ALTER TABLE {table} ALTER COLUMN embedding TYPE vector(1024)")
        # Restore NULLs so rows remain valid (no truncated 384-dim vectors).
        op.execute(f"UPDATE {table} SET embedding = NULL WHERE embedding IS NOT NULL")

    # 3. Recrear índices HNSW con dimensión 1024.
    for index_name, table_name in HNSW_INDEXES:
        op.create_index(
            index_name,
            table_name,
            ["embedding"],
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        )
