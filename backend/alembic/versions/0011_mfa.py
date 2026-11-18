"""Optional TOTP two-factor sign-in (Phase 8a, FR-AUTH-07).

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-18

- app_user: pending secret during enrolment, enabled time, hashed recovery codes and
  the last accepted time step (replay protection). `mfa_secret` exists since 0002.
- app_setting: `mfa_required_for_admins` (Admin setting, default off).

Migration policy (architecture 4.2): additive only, never edit a released
migration, and keep a working downgrade.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("app_user", sa.Column("mfa_pending_secret", sa.Text(), nullable=True))
    op.add_column(
        "app_user", sa.Column("mfa_enabled_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "app_user",
        sa.Column("mfa_recovery_codes", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column("app_user", sa.Column("mfa_last_counter", sa.BigInteger(), nullable=True))
    op.add_column(
        "app_setting",
        sa.Column("mfa_required_for_admins", sa.Boolean(), server_default="false", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("app_setting", "mfa_required_for_admins")
    op.drop_column("app_user", "mfa_last_counter")
    op.drop_column("app_user", "mfa_recovery_codes")
    op.drop_column("app_user", "mfa_enabled_at")
    op.drop_column("app_user", "mfa_pending_secret")
