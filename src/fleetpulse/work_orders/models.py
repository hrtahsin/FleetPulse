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
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from fleetpulse.shared.models import Base, TimestampMixin, UUIDPrimaryKeyMixin
from fleetpulse.work_orders.types import WorkOrderCostKind, WorkOrderPriority, WorkOrderStatus

_PRIORITIES = ", ".join(f"'{value.value}'" for value in WorkOrderPriority)
_STATUSES = ", ".join(f"'{value.value}'" for value in WorkOrderStatus)
_COST_KINDS = ", ".join(f"'{value.value}'" for value in WorkOrderCostKind)


class WorkOrder(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "work_orders"
    __table_args__ = (
        CheckConstraint(f"priority IN ({_PRIORITIES})", name="valid_priority"),
        CheckConstraint(f"status IN ({_STATUSES})", name="valid_status"),
        CheckConstraint("number > 0", name="positive_number"),
        CheckConstraint("version >= 1", name="positive_version"),
        CheckConstraint("labour_hours >= 0", name="nonnegative_labour_hours"),
        CheckConstraint("labour_cost >= 0", name="nonnegative_labour_cost"),
        CheckConstraint("parts_cost >= 0", name="nonnegative_parts_cost"),
        CheckConstraint(
            "source_defect_id IS NOT NULL OR maintenance_schedule_id IS NOT NULL",
            name="source_required",
        ),
        UniqueConstraint("organization_id", "number"),
        UniqueConstraint("source_defect_id"),
        UniqueConstraint("maintenance_schedule_id"),
        Index(
            "ix_work_orders_org_status_mechanic",
            "organization_id",
            "status",
            "assigned_mechanic_membership_id",
        ),
        Index("ix_work_orders_org_vehicle", "organization_id", "vehicle_id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    vehicle_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("vehicles.id", ondelete="RESTRICT"), nullable=False
    )
    source_defect_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("defects.id", ondelete="RESTRICT"), nullable=True
    )
    maintenance_schedule_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("maintenance_schedules.id", ondelete="RESTRICT"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[WorkOrderPriority] = mapped_column(String(20), nullable=False)
    status: Mapped[WorkOrderStatus] = mapped_column(String(24), nullable=False)
    assigned_mechanic_membership_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organization_memberships.id", ondelete="RESTRICT"), nullable=True
    )
    labour_hours: Mapped[Decimal] = mapped_column(
        Numeric(8, 2), nullable=False, default=Decimal("0.00")
    )
    labour_cost: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0.00")
    )
    parts_cost: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0.00")
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )


class WorkOrderNote(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "work_order_notes"
    __table_args__ = (
        Index(
            "ix_work_order_notes_org_order_created",
            "organization_id",
            "work_order_id",
            "created_at",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    work_order_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("work_orders.id", ondelete="CASCADE"), nullable=False
    )
    author_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class WorkOrderCostItem(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "work_order_cost_items"
    __table_args__ = (
        CheckConstraint(f"kind IN ({_COST_KINDS})", name="valid_kind"),
        CheckConstraint("quantity > 0", name="positive_quantity"),
        CheckConstraint("unit_cost >= 0", name="nonnegative_unit_cost"),
        Index("ix_work_order_cost_items_org_order", "organization_id", "work_order_id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    work_order_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("work_orders.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[WorkOrderCostKind] = mapped_column(String(20), nullable=False)
    description: Mapped[str] = mapped_column(String(180), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
