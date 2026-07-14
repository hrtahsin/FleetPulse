from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from fleetpulse.shared.models import Base, TimestampMixin, UUIDPrimaryKeyMixin
from fleetpulse.vehicles.status import VehicleStatus

_STATUS_VALUES = ", ".join(f"'{status.value}'" for status in VehicleStatus)


class Vehicle(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "vehicles"
    __table_args__ = (
        CheckConstraint("odometer_km >= 0", name="nonnegative_odometer"),
        CheckConstraint("model_year BETWEEN 1886 AND 2100", name="valid_model_year"),
        CheckConstraint(f"status IN ({_STATUS_VALUES})", name="valid_status"),
        UniqueConstraint("organization_id", "unit_number"),
        Index(
            "uq_vehicles_organization_id_vin",
            "organization_id",
            "vin",
            unique=True,
            postgresql_where=text("vin IS NOT NULL"),
        ),
        Index("ix_vehicles_organization_id_status", "organization_id", "status"),
        Index("ix_vehicles_organization_id_id", "organization_id", "id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    unit_number: Mapped[str] = mapped_column(String(40), nullable=False)
    vin: Mapped[str | None] = mapped_column(String(17), nullable=True)
    registration: Mapped[str | None] = mapped_column(String(40), nullable=True)
    make: Mapped[str] = mapped_column(String(80), nullable=False)
    model: Mapped[str] = mapped_column(String(80), nullable=False)
    model_year: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    fuel_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    odometer_km: Mapped[Decimal] = mapped_column(Numeric(12, 1), nullable=False, default=Decimal(0))
    status: Mapped[VehicleStatus] = mapped_column(
        String(30), nullable=False, default=VehicleStatus.AVAILABLE
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class VehicleAssignment(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "vehicle_assignments"
    __table_args__ = (
        CheckConstraint("ends_at IS NULL OR ends_at > starts_at", name="valid_assignment_window"),
        Index(
            "ix_vehicle_assignments_organization_id_vehicle_id_starts_at",
            "organization_id",
            "vehicle_id",
            "starts_at",
        ),
        Index(
            "ix_vehicle_assignments_organization_id_driver_membership_id",
            "organization_id",
            "driver_membership_id",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    vehicle_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("vehicles.id", ondelete="CASCADE"), nullable=False
    )
    driver_membership_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organization_memberships.id", ondelete="CASCADE"), nullable=False
    )
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class VehicleStatusHistory(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "vehicle_status_history"
    __table_args__ = (
        CheckConstraint(
            f"from_status IS NULL OR from_status IN ({_STATUS_VALUES})",
            name="valid_from_status",
        ),
        CheckConstraint(f"to_status IN ({_STATUS_VALUES})", name="valid_to_status"),
        Index(
            "ix_vehicle_status_history_organization_id_vehicle_id_created_at",
            "organization_id",
            "vehicle_id",
            "created_at",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    vehicle_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("vehicles.id", ondelete="CASCADE"), nullable=False
    )
    from_status: Mapped[VehicleStatus | None] = mapped_column(String(30), nullable=True)
    to_status: Mapped[VehicleStatus] = mapped_column(String(30), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(80), nullable=False)
    reason_reference_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    changed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
