"""The free model is the assistant's default (Phase 10, ADR 0031; owner, 2026-11-22).

Revision ID: 0014
Revises: 0013
Create Date: 2026-11-22

- app_setting.ai_model: the default becomes `nemotron-3-ultra-free` (the free NVIDIA
  Nemotron 3 Ultra through OpenRouter) instead of `gpt-oss-120b`.
- An installation still on the old default is switched to the new one. Release 1.1 has
  not been released, so `gpt-oss-120b` there is the value 0013 set, not an Admin's
  choice. An Admin can choose any catalog model again in Settings.

Migration policy (architecture 4.2): additive only, never edit a released
migration, and keep a working downgrade.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("app_setting", "ai_model", server_default="nemotron-3-ultra-free")
    op.execute(
        sa.text(
            "UPDATE app_setting SET ai_model = 'nemotron-3-ultra-free' "
            "WHERE ai_model = 'gpt-oss-120b'"
        )
    )


def downgrade() -> None:
    op.alter_column("app_setting", "ai_model", server_default="gpt-oss-120b")
    op.execute(
        sa.text(
            "UPDATE app_setting SET ai_model = 'gpt-oss-120b' "
            "WHERE ai_model = 'nemotron-3-ultra-free'"
        )
    )
