"""Activities, tasks and timeline events (Phase 4b).

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-17

- activity: notes, calls, meetings, emails and tasks (FR-ACT-01, 02), linked to
  at least one lead, opportunity, organization or contact (check constraint);
  a partial index serves "my open tasks".
- timeline_event: system events for record timelines (FR-ACT-03), written by
  the activity module's domain-event subscriber (ADR 0020).

Migration policy (architecture 4.2): additive only, never edit a released
migration, and keep a working downgrade.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "timeline_event",
        sa.Column("entity_type", sa.String(length=30), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=30), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column(
            "data",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["actor_id"], ["app_user.id"], name=op.f("fk_timeline_event_actor_id_app_user")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_timeline_event")),
    )
    op.create_index(
        "ix_timeline_event_entity",
        "timeline_event",
        ["entity_type", "entity_id", "occurred_at"],
        unique=False,
    )
    op.create_table(
        "activity",
        sa.Column("type", sa.String(length=10), nullable=False),
        sa.Column("subject", sa.String(length=200), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("done_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("assignee_id", sa.Uuid(), nullable=True),
        sa.Column("lead_id", sa.Uuid(), nullable=True),
        sa.Column("opportunity_id", sa.Uuid(), nullable=True),
        sa.Column("organization_id", sa.Uuid(), nullable=True),
        sa.Column("contact_id", sa.Uuid(), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "type IN ('note', 'call', 'meeting', 'email', 'task')", name=op.f("ck_activity_type")
        ),
        sa.CheckConstraint(
            "num_nonnulls(lead_id, opportunity_id, organization_id, contact_id) >= 1",
            name=op.f("ck_activity_has_link"),
        ),
        sa.ForeignKeyConstraint(
            ["assignee_id"], ["app_user.id"], name=op.f("fk_activity_assignee_id_app_user")
        ),
        sa.ForeignKeyConstraint(
            ["contact_id"], ["contact.id"], name=op.f("fk_activity_contact_id_contact")
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["app_user.id"], name=op.f("fk_activity_created_by_app_user")
        ),
        sa.ForeignKeyConstraint(["lead_id"], ["lead.id"], name=op.f("fk_activity_lead_id_lead")),
        sa.ForeignKeyConstraint(
            ["opportunity_id"],
            ["opportunity.id"],
            name=op.f("fk_activity_opportunity_id_opportunity"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organization.id"],
            name=op.f("fk_activity_organization_id_organization"),
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["app_user.id"], name=op.f("fk_activity_owner_id_app_user")
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"], ["app_user.id"], name=op.f("fk_activity_updated_by_app_user")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_activity")),
    )
    op.create_index(
        "ix_activity_assignee_open_tasks",
        "activity",
        ["assignee_id", "due_at"],
        unique=False,
        postgresql_where=sa.text("done_at IS NULL"),
    )
    op.create_index("ix_activity_contact_id", "activity", ["contact_id"], unique=False)
    op.create_index("ix_activity_lead_id", "activity", ["lead_id"], unique=False)
    op.create_index("ix_activity_opportunity_id", "activity", ["opportunity_id"], unique=False)
    op.create_index("ix_activity_organization_id", "activity", ["organization_id"], unique=False)
    op.create_index("ix_activity_owner_id", "activity", ["owner_id"], unique=False)
    op.create_index("ix_activity_updated_at_id", "activity", ["updated_at", "id"], unique=False)
    op.execute(
        "CREATE TRIGGER trg_activity_updated_at BEFORE UPDATE ON activity "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )


def downgrade() -> None:
    op.drop_index("ix_activity_updated_at_id", table_name="activity")
    op.drop_index("ix_activity_owner_id", table_name="activity")
    op.drop_index("ix_activity_organization_id", table_name="activity")
    op.drop_index("ix_activity_opportunity_id", table_name="activity")
    op.drop_index("ix_activity_lead_id", table_name="activity")
    op.drop_index("ix_activity_contact_id", table_name="activity")
    op.drop_index(
        "ix_activity_assignee_open_tasks",
        table_name="activity",
        postgresql_where=sa.text("done_at IS NULL"),
    )
    op.drop_table("activity")
    op.drop_index("ix_timeline_event_entity", table_name="timeline_event")
    op.drop_table("timeline_event")
