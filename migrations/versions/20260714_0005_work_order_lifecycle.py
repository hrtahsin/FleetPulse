"""Create work order lifecycle tables.

Revision ID: 20260714_0005
Revises: 20260714_0004
Create Date: 2026-07-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260714_0005"
down_revision: str | None = "20260714_0004"
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
        "work_orders",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("vehicle_id", sa.Uuid(), nullable=False),
        sa.Column("source_defect_id", sa.Uuid(), nullable=True),
        sa.Column("maintenance_schedule_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(length=180), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("priority", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("assigned_mechanic_membership_id", sa.Uuid(), nullable=True),
        sa.Column("labour_hours", sa.Numeric(precision=8, scale=2), nullable=False),
        sa.Column("labour_cost", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("parts_cost", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint("labour_cost >= 0", name=op.f("ck_work_orders_nonnegative_labour_cost")),
        sa.CheckConstraint(
            "labour_hours >= 0", name=op.f("ck_work_orders_nonnegative_labour_hours")
        ),
        sa.CheckConstraint("number > 0", name=op.f("ck_work_orders_positive_number")),
        sa.CheckConstraint("parts_cost >= 0", name=op.f("ck_work_orders_nonnegative_parts_cost")),
        sa.CheckConstraint(
            "priority IN ('low', 'normal', 'high', 'critical')",
            name=op.f("ck_work_orders_valid_priority"),
        ),
        sa.CheckConstraint(
            "source_defect_id IS NOT NULL OR maintenance_schedule_id IS NOT NULL",
            name=op.f("ck_work_orders_source_required"),
        ),
        sa.CheckConstraint(
            "status IN ('reported', 'triaged', 'approved', 'in_progress', "
            "'waiting_parts', 'completed', 'verified', 'closed', 'cancelled')",
            name=op.f("ck_work_orders_valid_status"),
        ),
        sa.CheckConstraint("version >= 1", name=op.f("ck_work_orders_positive_version")),
        sa.ForeignKeyConstraint(
            ["assigned_mechanic_membership_id"],
            ["organization_memberships.id"],
            name=op.f("fk_work_orders_assigned_mechanic_membership_id_organization_memberships"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name=op.f("fk_work_orders_created_by_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["maintenance_schedule_id"],
            ["maintenance_schedules.id"],
            name=op.f("fk_work_orders_maintenance_schedule_id_maintenance_schedules"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_work_orders_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_defect_id"],
            ["defects.id"],
            name=op.f("fk_work_orders_source_defect_id_defects"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["vehicle_id"],
            ["vehicles.id"],
            name=op.f("fk_work_orders_vehicle_id_vehicles"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_work_orders")),
        sa.UniqueConstraint(
            "maintenance_schedule_id", name=op.f("uq_work_orders_maintenance_schedule_id")
        ),
        sa.UniqueConstraint(
            "organization_id", "number", name=op.f("uq_work_orders_organization_id")
        ),
        sa.UniqueConstraint("source_defect_id", name=op.f("uq_work_orders_source_defect_id")),
    )
    op.create_index(
        "ix_work_orders_org_status_mechanic",
        "work_orders",
        ["organization_id", "status", "assigned_mechanic_membership_id"],
    )
    op.create_index("ix_work_orders_org_vehicle", "work_orders", ["organization_id", "vehicle_id"])

    op.create_table(
        "work_order_notes",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("work_order_id", sa.Uuid(), nullable=False),
        sa.Column("author_user_id", sa.Uuid(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["author_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["work_order_id"], ["work_orders.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_work_order_notes")),
    )
    op.create_index(
        "ix_work_order_notes_org_order_created",
        "work_order_notes",
        ["organization_id", "work_order_id", "created_at"],
    )

    op.create_table(
        "work_order_cost_items",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("work_order_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("description", sa.String(length=180), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("unit_cost", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "kind IN ('part', 'labour', 'other')",
            name=op.f("ck_work_order_cost_items_valid_kind"),
        ),
        sa.CheckConstraint("quantity > 0", name=op.f("ck_work_order_cost_items_positive_quantity")),
        sa.CheckConstraint(
            "unit_cost >= 0", name=op.f("ck_work_order_cost_items_nonnegative_unit_cost")
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["work_order_id"], ["work_orders.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_work_order_cost_items")),
    )
    op.create_index(
        "ix_work_order_cost_items_org_order",
        "work_order_cost_items",
        ["organization_id", "work_order_id"],
    )


def downgrade() -> None:
    op.drop_table("work_order_cost_items")
    op.drop_table("work_order_notes")
    op.drop_table("work_orders")
