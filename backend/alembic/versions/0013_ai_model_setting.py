"""The Admin's choice of AI model (Phase 10, FR-AI-10, ADR 0031).

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-22

- app_setting: `ai_model`, a catalog id from app.llm.models (default `gpt-oss-120b`,
  the model used until now). Validated by the application, not by the database: the
  catalog changes with code, a constraint would need a migration per model.

Migration policy (architecture 4.2): additive only, never edit a released
migration, and keep a working downgrade.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "app_setting",
        sa.Column("ai_model", sa.String(64), nullable=False, server_default="gpt-oss-120b"),
    )


def downgrade() -> None:
    op.drop_column("app_setting", "ai_model")
