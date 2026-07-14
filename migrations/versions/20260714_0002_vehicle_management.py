"""Create vehicle management tables.

Revision ID: 20260714_0002
Revises: 20260714_0001
Create Date: 2026-07-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260714_0002"
down_revision: str | Sequence[str] | None = "20260714_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

VEHICLE_STATUSES = (
    "'available', 'in_service', 'maintenance_due', 'under_repair', 'out_of_service', 'retired'"
)


def upgrade() -> None:
    op.create_table(
        "vehicles",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("unit_number", sa.String(length=40), nullable=False),
        sa.Column("vin", sa.String(length=17), nullable=True),
        sa.Column("registration", sa.String(length=40), nullable=True),
        sa.Column("make", sa.String(length=80), nullable=False),
        sa.Column("model", sa.String(length=80), nullable=False),
        sa.Column("model_year", sa.SmallInteger(), nullable=False),
        sa.Column("fuel_type", sa.String(length=30), nullable=True),
        sa.Column("odometer_km", sa.Numeric(precision=12, scale=1), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint("odometer_km >= 0", name=op.f("ck_vehicles_nonnegative_odometer")),
        sa.CheckConstraint(
            "model_year BETWEEN 1886 AND 2100", name=op.f("ck_vehicles_valid_model_year")
        ),
        sa.CheckConstraint(
            f"status IN ({VEHICLE_STATUSES})", name=op.f("ck_vehicles_valid_status")
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_vehicles_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_vehicles")),
        sa.UniqueConstraint(
            "organization_id", "unit_number", name=op.f("uq_vehicles_organization_id")
        ),
    )
    op.create_index(
        "ix_vehicles_organization_id_id", "vehicles", ["organization_id", "id"], unique=False
    )
    op.create_index(
        "ix_vehicles_organization_id_status",
        "vehicles",
        ["organization_id", "status"],
        unique=False,
    )
    op.create_index(
        "uq_vehicles_organization_id_vin",
        "vehicles",
        ["organization_id", "vin"],
        unique=True,
        postgresql_where=sa.text("vin IS NOT NULL"),
    )

    op.create_table(
        "vehicle_assignments",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("vehicle_id", sa.Uuid(), nullable=False),
        sa.Column("driver_membership_id", sa.Uuid(), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "ends_at IS NULL OR ends_at > starts_at",
            name=op.f("ck_vehicle_assignments_valid_assignment_window"),
        ),
        sa.ForeignKeyConstraint(
            ["driver_membership_id"],
            ["organization_memberships.id"],
            name=op.f("fk_vehicle_assignments_driver_membership_id_organization_memberships"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_vehicle_assignments_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["vehicle_id"],
            ["vehicles.id"],
            name=op.f("fk_vehicle_assignments_vehicle_id_vehicles"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_vehicle_assignments")),
    )
    op.create_index(
        "ix_vehicle_assignments_organization_id_driver_membership_id",
        "vehicle_assignments",
        ["organization_id", "driver_membership_id"],
        unique=False,
    )
    op.create_index(
        "ix_vehicle_assignments_organization_id_vehicle_id_starts_at",
        "vehicle_assignments",
        ["organization_id", "vehicle_id", "starts_at"],
        unique=False,
    )

    op.create_table(
        "vehicle_status_history",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("vehicle_id", sa.Uuid(), nullable=False),
        sa.Column("from_status", sa.String(length=30), nullable=True),
        sa.Column("to_status", sa.String(length=30), nullable=False),
        sa.Column("reason_code", sa.String(length=80), nullable=False),
        sa.Column("reason_reference_id", sa.Uuid(), nullable=True),
        sa.Column("changed_by_user_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            f"from_status IS NULL OR from_status IN ({VEHICLE_STATUSES})",
            name=op.f("ck_vehicle_status_history_valid_from_status"),
        ),
        sa.CheckConstraint(
            f"to_status IN ({VEHICLE_STATUSES})",
            name=op.f("ck_vehicle_status_history_valid_to_status"),
        ),
        sa.ForeignKeyConstraint(
            ["changed_by_user_id"],
            ["users.id"],
            name=op.f("fk_vehicle_status_history_changed_by_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_vehicle_status_history_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["vehicle_id"],
            ["vehicles.id"],
            name=op.f("fk_vehicle_status_history_vehicle_id_vehicles"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_vehicle_status_history")),
    )
    op.create_index(
        "ix_vehicle_status_history_organization_id_vehicle_id_created_at",
        "vehicle_status_history",
        ["organization_id", "vehicle_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("vehicle_status_history")
    op.drop_table("vehicle_assignments")
    op.drop_table("vehicles")
