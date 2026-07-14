from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from fleetpulse.defects.types import DefectSeverity, DefectStatus
from fleetpulse.shared.models import Base, TimestampMixin, UUIDPrimaryKeyMixin

_SEVERITIES = ", ".join(f"'{value.value}'" for value in DefectSeverity)
_STATUSES = ", ".join(f"'{value.value}'" for value in DefectStatus)


class Defect(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "defects"
    __table_args__ = (
        CheckConstraint(f"severity IN ({_SEVERITIES})", name="valid_severity"),
        CheckConstraint(f"status IN ({_STATUSES})", name="valid_status"),
        Index(
            "ix_defects_organization_id_status_severity",
            "organization_id",
            "status",
            "severity",
        ),
        Index("ix_defects_organization_id_vehicle_id", "organization_id", "vehicle_id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    inspection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("inspections.id", ondelete="CASCADE"), nullable=False
    )
    inspection_response_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("inspection_responses.id", ondelete="SET NULL"), nullable=True
    )
    vehicle_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("vehicles.id", ondelete="CASCADE"), nullable=False
    )
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[DefectSeverity] = mapped_column(String(20), nullable=False)
    status: Mapped[DefectStatus] = mapped_column(
        String(20), nullable=False, default=DefectStatus.OPEN
    )
    reported_by_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
