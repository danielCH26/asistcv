"""Rename ``cv_adaptations.jd_text_encrypted`` to ``jd_text``.

Revision ID: 019_rename_adaptations_jd_text
Revises: 018_audit_claim_policy
Create Date: 2026-09-30

Why
---
Migration 015 created the column as ``BYTEA`` and PR2b filled it with raw
UTF-8 bytes (``payload.jd_text.encode("utf-8")``). Nothing ever encrypted
it, but the name asserted that it did — the worst kind of debt, because a
reviewer or a compliance scan reading the schema assumes a protection that
does not exist. Plaintext here is a deliberate, consistent choice:
``users_cvs.raw_text``, ``users_cvs.raw_blob`` and ``audit_uploads.cv_text``
are plaintext too.

The maintainer's call is RENAME, not encrypt. The goal is that the name
stops lying; implementing encryption is a separate, larger change.

Scope
-----
A pure rename. No data is rewritten, no type changes (``BYTEA`` stays
``BYTEA``), no index or constraint is touched — the column is not
referenced by any index, default, check, view or policy, so a rename is
enough. ``016_rls_cv_adaptations`` is unaffected: its policies key on
``owner_user_id`` / ``parent_cv_id``, not on this column.

NOTE: the slug drops the ``cv_`` infix (``019_rename_adaptations_jd_text``,
30 chars) for the same reason 017 did — ``alembic_version.version_num`` is
``VARCHAR(32)`` (migration 001) and ``019_rename_cv_adaptations_jd_text``
is 33.

Reversibility
-------------
``downgrade()`` renames the column back. Nothing is lost in either
direction: the bytes are identical on both sides of the rename.
"""
from collections.abc import Sequence

from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "019_rename_adaptations_jd_text"
down_revision: str | Sequence[str] | None = "018_audit_claim_policy"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "cv_adaptations"
_OLD_NAME = "jd_text_encrypted"
_NEW_NAME = "jd_text"


def upgrade() -> None:
    """``jd_text_encrypted`` -> ``jd_text``. Same column, same BYTEA type."""
    op.alter_column(
        _TABLE,
        _OLD_NAME,
        new_column_name=_NEW_NAME,
        existing_type=postgresql.BYTEA(),
        existing_nullable=True,
    )


def downgrade() -> None:
    """``jd_text`` -> ``jd_text_encrypted``. Restores the pre-019 name."""
    op.alter_column(
        _TABLE,
        _NEW_NAME,
        new_column_name=_OLD_NAME,
        existing_type=postgresql.BYTEA(),
        existing_nullable=True,
    )
