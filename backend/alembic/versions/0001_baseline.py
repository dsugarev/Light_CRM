"""Baseline: database extensions used by every later migration.

Revision ID: 0001
Revises:
Create Date: 2026-11-17

pg_trgm backs partial-match search over Latin and Cyrillic text
(architecture 4.1). It is a trusted extension, so the database owner (the
migration role) can create it without superuser rights.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")


def downgrade() -> None:
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
