"""Make audit_uploads.jd_text optional for CV-only audits.

The free audit funnel now works without a Job Description: jd_text is
only stored when the visitor provides one (jd_directed mode); CV-only
audits store NULL.

Revision ID: 012_audit_jd_optional
Revises: 011_rls_policies
Create Date: 2026-09-24
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "012_audit_jd_optional"
down_revision: str = "011_rls_policies"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "audit_uploads",
        "jd_text",
        existing_type=sa.Text(),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "audit_uploads",
        "jd_text",
        existing_type=sa.Text(),
        nullable=False,
    )
