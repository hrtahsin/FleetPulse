"""Create maintenance rules and schedules.

Revision ID: 20260714_0004
Revises: 20260714_0003
Create Date: 2026-07-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260714_0004"
down_revision: str | None = "20260714_0003"
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
        "maintenance_rules",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("vehicle_id", sa.Uuid(), nullable=True),
        sa.Column("interval_km", sa.Numeric(precision=12, scale=1), nullable=True),
        sa.Column("interval_days", sa.Integer(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "interval_days IS NULL OR interval_days > 0",
            name=op.f("ck_maintenance_rules_positive_interval_days"),
        ),
        sa.CheckConstraint(
            "interval_km IS NULL OR interval_km > 0",
            name=op.f("ck_maintenance_rules_positive_interval_km"),
        ),
        sa.CheckConstraint(
            "interval_km IS NOT NULL OR interval_days IS NOT NULL",
            name=op.f("ck_maintenance_rules_interval_required"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_maintenance_rules_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["vehicle_id"],
            ["vehicles.id"],
            name=op.f("fk_maintenance_rules_vehicle_id_vehicles"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_maintenance_rules")),
    )
    op.create_index(
        "ix_maintenance_rules_org_active",
        "maintenance_rules",
        ["organization_id", "active"],
        unique=False,
    )
    op.create_index(
        "ix_maintenance_rules_org_vehicle",
        "maintenance_rules",
        ["organization_id", "vehicle_id"],
        unique=False,
    )

    op.create_table(
        "maintenance_schedules",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("vehicle_id", sa.Uuid(), nullable=False),
        sa.Column("maintenance_rule_id", sa.Uuid(), nullable=False),
        sa.Column("last_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "last_completed_odometer_km",
            sa.Numeric(precision=12, scale=1),
            nullable=True,
        ),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("due_odometer_km", sa.Numeric(precision=12, scale=1), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "due_odometer_km IS NULL OR due_odometer_km >= 0",
            name=op.f("ck_maintenance_schedules_nonnegative_due_odometer"),
        ),
        sa.CheckConstraint(
            "last_completed_odometer_km IS NULL OR last_completed_odometer_km >= 0",
            name=op.f("ck_maintenance_schedules_nonnegative_completed_odometer"),
        ),
        sa.CheckConstraint(
            "status IN ('upcoming', 'due', 'overdue', 'completed', 'dismissed')",
            name=op.f("ck_maintenance_schedules_valid_status"),
        ),
        sa.ForeignKeyConstraint(
            ["maintenance_rule_id"],
            ["maintenance_rules.id"],
            name=op.f("fk_maintenance_schedules_maintenance_rule_id_maintenance_rules"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_maintenance_schedules_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["vehicle_id"],
            ["vehicles.id"],
            name=op.f("fk_maintenance_schedules_vehicle_id_vehicles"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_maintenance_schedules")),
        sa.UniqueConstraint(
            "vehicle_id",
            "maintenance_rule_id",
            name=op.f("uq_maintenance_schedules_vehicle_id"),
        ),
    )
    op.create_index(
        "ix_maintenance_schedules_org_status_due",
        "maintenance_schedules",
        ["organization_id", "status", "due_at"],
        unique=False,
    )
    op.create_index(
        "ix_maintenance_schedules_org_vehicle",
        "maintenance_schedules",
        ["organization_id", "vehicle_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("maintenance_schedules")
    op.drop_table("maintenance_rules")
