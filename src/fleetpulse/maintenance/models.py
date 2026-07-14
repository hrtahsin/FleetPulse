from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from fleetpulse.maintenance.types import MaintenanceScheduleStatus
from fleetpulse.shared.models import Base, TimestampMixin, UUIDPrimaryKeyMixin

_SCHEDULE_STATUSES = ", ".join(f"'{status.value}'" for status in MaintenanceScheduleStatus)


class MaintenanceRule(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "maintenance_rules"
    __table_args__ = (
        CheckConstraint(
            "interval_km IS NOT NULL OR interval_days IS NOT NULL",
            name="interval_required",
        ),
        CheckConstraint(
            "interval_km IS NULL OR interval_km > 0",
            name="positive_interval_km",
        ),
        CheckConstraint(
            "interval_days IS NULL OR interval_days > 0",
            name="positive_interval_days",
        ),
        Index(
            "ix_maintenance_rules_org_active",
            "organization_id",
            "active",
        ),
        Index(
            "ix_maintenance_rules_org_vehicle",
            "organization_id",
            "vehicle_id",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    vehicle_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("vehicles.id", ondelete="CASCADE"), nullable=True
    )
    interval_km: Mapped[Decimal | None] = mapped_column(Numeric(12, 1), nullable=True)
    interval_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class MaintenanceSchedule(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "maintenance_schedules"
    __table_args__ = (
        CheckConstraint(
            f"status IN ({_SCHEDULE_STATUSES})",
            name="valid_status",
        ),
        CheckConstraint(
            "last_completed_odometer_km IS NULL OR last_completed_odometer_km >= 0",
            name="nonnegative_completed_odometer",
        ),
        CheckConstraint(
            "due_odometer_km IS NULL OR due_odometer_km >= 0",
            name="nonnegative_due_odometer",
        ),
        UniqueConstraint("vehicle_id", "maintenance_rule_id"),
        Index(
            "ix_maintenance_schedules_org_status_due",
            "organization_id",
            "status",
            "due_at",
        ),
        Index(
            "ix_maintenance_schedules_org_vehicle",
            "organization_id",
            "vehicle_id",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    vehicle_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("vehicles.id", ondelete="CASCADE"), nullable=False
    )
    maintenance_rule_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("maintenance_rules.id", ondelete="CASCADE"), nullable=False
    )
    last_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_completed_odometer_km: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 1), nullable=True
    )
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    due_odometer_km: Mapped[Decimal | None] = mapped_column(Numeric(12, 1), nullable=True)
    status: Mapped[MaintenanceScheduleStatus] = mapped_column(String(20), nullable=False)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
