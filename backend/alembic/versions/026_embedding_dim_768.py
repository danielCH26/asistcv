"""Cambiar embedding de vector(384) a vector(768) en 4 tablas.

Issue #101 / pivote Gemini: la inferencia local (fastembed) no sostenía
los límites de la instancia free de Render (512MB RAM / 0.1 CPU — el
container se mató a mitad del primer match). El provider nuevo es
``gemini-embedding-001`` vía REST (API key AI Studio free, sin tarjeta)
con ``outputDimensionality 768``, incompatible con las columnas de 384.

Upgrade:
  1. Dropea los índices HNSW (dimensionados en 384).
  2. SET embedding = NULL en las 4 tablas (vectores de 384 no son
     convertibles a 768 — match.py re-embeddea on-demand; hay ~1 CV en
     producción).
  3. ALTER TYPE a vector(768) con USING embedding::text::vector.
  4. Recrear índices HNSW con la nueva dimensión.

Downgrade:
  1. Dropea los índices HNSW (dimensionados en 768).
  2. ALTER TYPE de vuelta a vector(384) con NULLs
     (data loss: los vectores de 768 no se convierten a 384).
  3. Recrear índices HNSW con dimensión 384.

users_cvs NO tiene índice HNSW (migración 004 no lo creó).
"""

from collections.abc import Sequence

from alembic import op

revision: str = "026_embedding_dim_768"
down_revision: str = "025_embedding_dim_384"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

# Tablas con columna embedding que reciben el ALTER TYPE.
VECTOR_TABLES = ("profiles", "job_descriptions", "analyses", "users_cvs")

# Tablas con índice HNSW sobre embedding (creado en migración 002).
# users_cvs NO tiene índice HNSW.
HNSW_INDEXES = (
    ("idx_profiles_embedding_hnsw", "profiles"),
    ("idx_jd_embedding_hnsw", "job_descriptions"),
    ("idx_analyses_embedding_hnsw", "analyses"),
)


def upgrade() -> None:
    # 1. Dropear índices HNSW (dimensionados para 384) antes del ALTER TYPE.
    for index_name, table_name in HNSW_INDEXES:
        op.drop_index(index_name, table_name=table_name)

    # 2. Nullear vectores existentes (384) — no son convertibles a 768.
    for table in VECTOR_TABLES:
        op.execute(f"UPDATE {table} SET embedding = NULL WHERE embedding IS NOT NULL")

    # 3. ALTER TYPE vector(384) → vector(768) con cast ::text::vector.
    for table in VECTOR_TABLES:
        op.execute(
            f"ALTER TABLE {table} "
            f"ALTER COLUMN embedding TYPE vector(768) "
            f"USING embedding::text::vector"
        )

    # 4. Recrear índices HNSW con la nueva dimensión 768.
    for index_name, table_name in HNSW_INDEXES:
        op.create_index(
            index_name,
            table_name,
            ["embedding"],
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        )


def downgrade() -> None:
    # 1. Dropear índices HNSW (dimensionados para 768).
    for index_name, table_name in HNSW_INDEXES:
        op.drop_index(index_name, table_name=table_name)

    # 2. ALTER TYPE vector(768) → vector(384) con NULLs.
    #    Data loss: los vectores de 768 dims no se convierten a 384.
    for table in VECTOR_TABLES:
        op.execute(f"ALTER TABLE {table} ALTER COLUMN embedding TYPE vector(384)")
        # Restore NULLs so rows remain valid (no truncated 768-dim vectors).
        op.execute(f"UPDATE {table} SET embedding = NULL WHERE embedding IS NOT NULL")

    # 3. Recrear índices HNSW con dimensión 384.
    for index_name, table_name in HNSW_INDEXES:
        op.create_index(
            index_name,
            table_name,
            ["embedding"],
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        )
