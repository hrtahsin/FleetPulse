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
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from fleetpulse.inspections.types import InspectionStatus, ResponseType
from fleetpulse.shared.models import Base, TimestampMixin, UUIDPrimaryKeyMixin

_RESPONSE_TYPES = ", ".join(f"'{value.value}'" for value in ResponseType)
_INSPECTION_STATUSES = ", ".join(f"'{value.value}'" for value in InspectionStatus)


class InspectionTemplate(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "inspection_templates"
    __table_args__ = (
        CheckConstraint("version >= 1", name="positive_version"),
        UniqueConstraint("organization_id", "name", "version"),
        Index(
            "ix_inspection_templates_organization_id_is_active",
            "organization_id",
            "is_active",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class InspectionTemplateItem(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "inspection_template_items"
    __table_args__ = (
        CheckConstraint(f"response_type IN ({_RESPONSE_TYPES})", name="valid_response_type"),
        CheckConstraint("sort_order >= 0", name="nonnegative_sort_order"),
        UniqueConstraint("template_id", "code"),
        Index(
            "ix_inspection_template_items_template_id_sort_order",
            "template_id",
            "sort_order",
        ),
    )

    template_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("inspection_templates.id", ondelete="CASCADE"), nullable=False
    )
    code: Mapped[str] = mapped_column(String(60), nullable=False)
    label: Mapped[str] = mapped_column(String(180), nullable=False)
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    response_type: Mapped[ResponseType] = mapped_column(String(20), nullable=False)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)


class Inspection(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "inspections"
    __table_args__ = (
        CheckConstraint("odometer_km >= 0", name="nonnegative_odometer"),
        CheckConstraint(f"status IN ({_INSPECTION_STATUSES})", name="valid_status"),
        UniqueConstraint("organization_id", "idempotency_key"),
        Index(
            "ix_inspections_organization_id_vehicle_id_submitted_at",
            "organization_id",
            "vehicle_id",
            "submitted_at",
        ),
        Index(
            "ix_inspections_org_driver_submitted_at",
            "organization_id",
            "driver_membership_id",
            "submitted_at",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    vehicle_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("vehicles.id", ondelete="CASCADE"), nullable=False
    )
    driver_membership_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organization_memberships.id", ondelete="RESTRICT"), nullable=False
    )
    template_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("inspection_templates.id", ondelete="RESTRICT"), nullable=False
    )
    odometer_km: Mapped[Decimal] = mapped_column(Numeric(12, 1), nullable=False)
    status: Mapped[InspectionStatus] = mapped_column(
        String(20), nullable=False, default=InspectionStatus.SUBMITTED
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class InspectionResponse(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "inspection_responses"
    __table_args__ = (UniqueConstraint("inspection_id", "template_item_id"),)

    inspection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("inspections.id", ondelete="CASCADE"), nullable=False
    )
    template_item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("inspection_template_items.id", ondelete="RESTRICT"), nullable=False
    )
    result: Mapped[str] = mapped_column(Text, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
