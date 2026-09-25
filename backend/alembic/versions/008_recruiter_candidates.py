"""
Add recruiter_candidates tables for external candidate management.

This migration creates the following tables:
- recruiter_candidates: External candidates managed by recruiters
- recruiter_candidates_cvs: CV documents for external candidates
- recruiter_analyses: Match analyses for candidates
- recruiter_audit_log: Audit log for recruiter actions

Revision ID: 008
Revises: 007
Create Date: 2024-01-15
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "008"
down_revision: str = "007"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    # Create recruiter_candidates_cvs table
    op.create_table(
        "recruiter_candidates_cvs",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("candidate_id", sa.BigInteger(), nullable=True),
        sa.Column("original_filename", sa.String(500), nullable=False),
        sa.Column("raw_blob", sa.LargeBinary(length=10485760), nullable=True),  # 10MB max
        sa.Column("raw_text", sa.Text(), nullable=True),
        sa.Column("structured", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_rc_cvs_candidate_id", "recruiter_candidates_cvs", ["candidate_id"])

    # Create recruiter_candidates table
    op.create_table(
        "recruiter_candidates",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("recruiter_id", sa.BigInteger(), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("phone", sa.String(50), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("cv_id", sa.BigInteger(), nullable=True),
        sa.Column("last_analysed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    # Add foreign key to users (recruiter)
    op.create_foreign_key(
        "fk_recruiter_candidates_recruiter",
        "recruiter_candidates",
        "users",
        ["recruiter_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # Add foreign key to recruiter_candidates_cvs
    op.create_foreign_key(
        "fk_recruiter_candidates_cv",
        "recruiter_candidates",
        "recruiter_candidates_cvs",
        ["cv_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # Unique constraint: one candidate per email per recruiter
    op.create_index(
        "idx_candidate_unique_per_recruiter",
        "recruiter_candidates",
        ["recruiter_id", sa.text("COALESCE(email, '')")],
        unique=True,
    )

    op.create_index("idx_candidate_recruiter", "recruiter_candidates", ["recruiter_id"])

    # Create recruiter_analyses table
    op.create_table(
        "recruiter_analyses",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("candidate_id", sa.BigInteger(), nullable=False),
        sa.Column("recruiter_id", sa.BigInteger(), nullable=False),
        sa.Column("jd_text", sa.Text(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("strengths", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("gaps", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("reasoning", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_foreign_key(
        "fk_recruiter_analyses_candidate",
        "recruiter_analyses",
        "recruiter_candidates",
        ["candidate_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.create_index("idx_recruiter_analyses_candidate", "recruiter_analyses", ["candidate_id"])
    op.create_index("idx_recruiter_analyses_recruiter", "recruiter_analyses", ["recruiter_id"])

    # Create recruiter_audit_log table (append-only)
    op.create_table(
        "recruiter_audit_log",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("recruiter_id", sa.BigInteger(), nullable=False),
        sa.Column("candidate_id", sa.BigInteger(), nullable=True),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index("idx_recruiter_audit_log_recruiter", "recruiter_audit_log", ["recruiter_id"])
    op.create_index("idx_recruiter_audit_log_candidate", "recruiter_audit_log", ["candidate_id"])

    # Add trigger to make recruiter_audit_log append-only
    op.execute("""
        CREATE OR REPLACE FUNCTION reject_modification() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'audit log is append-only';
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        CREATE TRIGGER trg_audit_log_immutable
        BEFORE UPDATE OR DELETE ON recruiter_audit_log
        FOR EACH ROW EXECUTE FUNCTION reject_modification();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_audit_log_immutable ON recruiter_audit_log")
    op.execute("DROP FUNCTION IF EXISTS reject_modification()")

    op.drop_index("idx_recruiter_audit_log_candidate", table_name="recruiter_audit_log")
    op.drop_index("idx_recruiter_audit_log_recruiter", table_name="recruiter_audit_log")
    op.drop_table("recruiter_audit_log")

    op.drop_index("idx_recruiter_analyses_recruiter", table_name="recruiter_analyses")
    op.drop_index("idx_recruiter_analyses_candidate", table_name="recruiter_analyses")
    op.drop_constraint("fk_recruiter_analyses_candidate", "recruiter_analyses", type_="foreignkey")
    op.drop_table("recruiter_analyses")

    op.drop_index("idx_candidate_recruiter", table_name="recruiter_candidates")
    op.drop_index("idx_candidate_unique_per_recruiter", table_name="recruiter_candidates")
    op.drop_constraint("fk_recruiter_candidates_cv", "recruiter_candidates", type_="foreignkey")
    op.drop_constraint("fk_recruiter_candidates_recruiter", "recruiter_candidates", type_="foreignkey")
    op.drop_table("recruiter_candidates")

    op.drop_index("idx_rc_cvs_candidate_id", table_name="recruiter_candidates_cvs")
    op.drop_table("recruiter_candidates_cvs")
