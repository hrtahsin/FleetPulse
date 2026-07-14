"""Create inspection safety-loop tables.

Revision ID: 20260714_0003
Revises: 20260714_0002
Create Date: 2026-07-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260714_0003"
down_revision: str | Sequence[str] | None = "20260714_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column[object]]:
    return [
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
    ]


def upgrade() -> None:
    op.create_table(
        "inspection_templates",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint("version >= 1", name=op.f("ck_inspection_templates_positive_version")),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_inspection_templates_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_inspection_templates")),
        sa.UniqueConstraint(
            "organization_id",
            "name",
            "version",
            name=op.f("uq_inspection_templates_organization_id"),
        ),
    )
    op.create_index(
        "ix_inspection_templates_organization_id_is_active",
        "inspection_templates",
        ["organization_id", "is_active"],
        unique=False,
    )

    op.create_table(
        "inspection_template_items",
        sa.Column("template_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=60), nullable=False),
        sa.Column("label", sa.String(length=180), nullable=False),
        sa.Column("category", sa.String(length=80), nullable=False),
        sa.Column("response_type", sa.String(length=20), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "response_type IN ('pass_fail', 'boolean', 'text', 'number')",
            name=op.f("ck_inspection_template_items_valid_response_type"),
        ),
        sa.CheckConstraint(
            "sort_order >= 0", name=op.f("ck_inspection_template_items_nonnegative_sort_order")
        ),
        sa.ForeignKeyConstraint(
            ["template_id"],
            ["inspection_templates.id"],
            name=op.f("fk_inspection_template_items_template_id_inspection_templates"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_inspection_template_items")),
        sa.UniqueConstraint(
            "template_id", "code", name=op.f("uq_inspection_template_items_template_id")
        ),
    )
    op.create_index(
        "ix_inspection_template_items_template_id_sort_order",
        "inspection_template_items",
        ["template_id", "sort_order"],
        unique=False,
    )

    op.create_table(
        "inspections",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("vehicle_id", sa.Uuid(), nullable=False),
        sa.Column("driver_membership_id", sa.Uuid(), nullable=False),
        sa.Column("template_id", sa.Uuid(), nullable=False),
        sa.Column("odometer_km", sa.Numeric(precision=12, scale=1), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint("odometer_km >= 0", name=op.f("ck_inspections_nonnegative_odometer")),
        sa.CheckConstraint(
            "status IN ('submitted', 'reviewed')", name=op.f("ck_inspections_valid_status")
        ),
        sa.ForeignKeyConstraint(
            ["driver_membership_id"],
            ["organization_memberships.id"],
            name=op.f("fk_inspections_driver_membership_id_organization_memberships"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_inspections_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["template_id"],
            ["inspection_templates.id"],
            name=op.f("fk_inspections_template_id_inspection_templates"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["vehicle_id"],
            ["vehicles.id"],
            name=op.f("fk_inspections_vehicle_id_vehicles"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_inspections")),
        sa.UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name=op.f("uq_inspections_organization_id"),
        ),
    )
    op.create_index(
        "ix_inspections_organization_id_driver_membership_id_submitted_at",
        "inspections",
        ["organization_id", "driver_membership_id", "submitted_at"],
        unique=False,
    )
    op.create_index(
        "ix_inspections_organization_id_vehicle_id_submitted_at",
        "inspections",
        ["organization_id", "vehicle_id", "submitted_at"],
        unique=False,
    )

    op.create_table(
        "inspection_responses",
        sa.Column("inspection_id", sa.Uuid(), nullable=False),
        sa.Column("template_item_id", sa.Uuid(), nullable=False),
        sa.Column("result", sa.Text(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["inspection_id"],
            ["inspections.id"],
            name=op.f("fk_inspection_responses_inspection_id_inspections"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["template_item_id"],
            ["inspection_template_items.id"],
            name=op.f("fk_inspection_responses_template_item_id_inspection_template_items"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_inspection_responses")),
        sa.UniqueConstraint(
            "inspection_id",
            "template_item_id",
            name=op.f("uq_inspection_responses_inspection_id"),
        ),
    )

    op.create_table(
        "defects",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("inspection_id", sa.Uuid(), nullable=False),
        sa.Column("inspection_response_id", sa.Uuid(), nullable=True),
        sa.Column("vehicle_id", sa.Uuid(), nullable=False),
        sa.Column("category", sa.String(length=80), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("reported_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "severity IN ('minor', 'major', 'critical')",
            name=op.f("ck_defects_valid_severity"),
        ),
        sa.CheckConstraint(
            "status IN ('open', 'triaged', 'in_repair', 'resolved', 'dismissed')",
            name=op.f("ck_defects_valid_status"),
        ),
        sa.ForeignKeyConstraint(
            ["inspection_id"],
            ["inspections.id"],
            name=op.f("fk_defects_inspection_id_inspections"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["inspection_response_id"],
            ["inspection_responses.id"],
            name=op.f("fk_defects_inspection_response_id_inspection_responses"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_defects_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["reported_by_user_id"],
            ["users.id"],
            name=op.f("fk_defects_reported_by_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["vehicle_id"],
            ["vehicles.id"],
            name=op.f("fk_defects_vehicle_id_vehicles"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_defects")),
    )
    op.create_index(
        "ix_defects_organization_id_status_severity",
        "defects",
        ["organization_id", "status", "severity"],
        unique=False,
    )
    op.create_index(
        "ix_defects_organization_id_vehicle_id",
        "defects",
        ["organization_id", "vehicle_id"],
        unique=False,
    )

    op.create_table(
        "notifications",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("recipient_user_id", sa.Uuid(), nullable=False),
        sa.Column("type", sa.String(length=80), nullable=False),
        sa.Column("title", sa.String(length=180), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("entity_type", sa.String(length=80), nullable=True),
        sa.Column("entity_id", sa.Uuid(), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_notifications_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["recipient_user_id"],
            ["users.id"],
            name=op.f("fk_notifications_recipient_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notifications")),
    )
    op.create_index(
        "ix_notifications_organization_id_recipient_user_id_unread",
        "notifications",
        ["organization_id", "recipient_user_id"],
        unique=False,
        postgresql_where=sa.text("read_at IS NULL"),
    )
    op.create_index(
        "ix_notifications_recipient_user_id_read_at_created_at",
        "notifications",
        ["recipient_user_id", "read_at", "created_at"],
        unique=False,
    )

    op.create_table(
        "audit_events",
        sa.Column("organization_id", sa.Uuid(), nullable=True),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("entity_type", sa.String(length=80), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=True),
        sa.Column("before_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("after_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("request_id", sa.Uuid(), nullable=True),
        sa.Column("ip_hash", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            name=op.f("fk_audit_events_actor_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_audit_events_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_events")),
    )
    op.create_index(
        "ix_audit_events_organization_id_entity_type_entity_id_created_at",
        "audit_events",
        ["organization_id", "entity_type", "entity_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "outbox_events",
        sa.Column("organization_id", sa.Uuid(), nullable=True),
        sa.Column("event_type", sa.String(length=120), nullable=False),
        sa.Column("aggregate_type", sa.String(length=80), nullable=False),
        sa.Column("aggregate_id", sa.Uuid(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_outbox_events")),
    )
    op.create_index(
        "ix_outbox_events_organization_id_aggregate_id",
        "outbox_events",
        ["organization_id", "aggregate_id"],
        unique=False,
    )
    op.create_index(
        "ix_outbox_events_unprocessed_occurred_at",
        "outbox_events",
        ["processed_at", "occurred_at"],
        unique=False,
        postgresql_where=sa.text("processed_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_table("outbox_events")
    op.drop_table("audit_events")
    op.drop_table("notifications")
    op.drop_table("defects")
    op.drop_table("inspection_responses")
    op.drop_table("inspections")
    op.drop_table("inspection_template_items")
    op.drop_table("inspection_templates")
