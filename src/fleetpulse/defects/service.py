import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import cast

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fleetpulse.audit.models import AuditEvent
from fleetpulse.defects.exceptions import (
    DefectHasActiveWorkOrderError,
    DefectNotFoundError,
    InvalidDefectTransitionError,
)
from fleetpulse.defects.models import Defect
from fleetpulse.defects.types import DefectSeverity, DefectStatus
from fleetpulse.maintenance.models import MaintenanceSchedule
from fleetpulse.maintenance.types import MaintenanceScheduleStatus
from fleetpulse.notifications.models import Notification
from fleetpulse.outbox.models import OutboxEvent
from fleetpulse.shared.database import get_session_factory
from fleetpulse.vehicles.models import Vehicle, VehicleStatusHistory
from fleetpulse.vehicles.status import VehicleStatus
from fleetpulse.work_orders.models import WorkOrder
from fleetpulse.work_orders.types import WorkOrderStatus


class DefectService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession] | None = None) -> None:
        self._session_factory = session_factory or get_session_factory()

    async def list(
        self,
        *,
        organization_id: uuid.UUID,
        status: DefectStatus | None,
        severity: DefectSeverity | None,
        vehicle_id: uuid.UUID | None,
        limit: int,
    ) -> Sequence[Defect]:
        statement: Select[tuple[Defect]] = select(Defect).where(
            Defect.organization_id == organization_id
        )
        if status is not None:
            statement = statement.where(Defect.status == status)
        if severity is not None:
            statement = statement.where(Defect.severity == severity)
        if vehicle_id is not None:
            statement = statement.where(Defect.vehicle_id == vehicle_id)
        statement = statement.order_by(Defect.created_at.desc(), Defect.id.desc()).limit(limit)
        async with self._session_factory() as session:
            return (await session.scalars(statement)).all()

    async def get(self, *, organization_id: uuid.UUID, defect_id: uuid.UUID) -> Defect:
        async with self._session_factory() as session:
            defect = cast(
                Defect | None,
                await session.scalar(
                    select(Defect).where(
                        Defect.organization_id == organization_id,
                        Defect.id == defect_id,
                    )
                ),
            )
        if defect is None:
            raise DefectNotFoundError
        return defect

    async def update_status(
        self,
        *,
        organization_id: uuid.UUID,
        defect_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        request_id: uuid.UUID,
        next_status: DefectStatus,
        resolution_note: str | None,
    ) -> Defect:
        now = datetime.now(UTC)
        async with self._session_factory() as session, session.begin():
            defect = cast(
                Defect | None,
                await session.scalar(
                    select(Defect)
                    .where(
                        Defect.organization_id == organization_id,
                        Defect.id == defect_id,
                    )
                    .with_for_update()
                ),
            )
            if defect is None:
                raise DefectNotFoundError
            current_status = DefectStatus(defect.status)
            allowed = {
                DefectStatus.OPEN: {DefectStatus.TRIAGED, DefectStatus.DISMISSED},
                DefectStatus.TRIAGED: {DefectStatus.DISMISSED},
            }
            if next_status not in allowed.get(current_status, set()):
                raise InvalidDefectTransitionError
            if next_status is DefectStatus.DISMISSED and await self._has_active_work_order(
                session, organization_id, defect.id
            ):
                raise DefectHasActiveWorkOrderError

            before = {
                "status": current_status.value,
                "resolution_note": defect.resolution_note,
            }
            defect.status = next_status
            defect.resolution_note = resolution_note.strip() if resolution_note else None
            if next_status is DefectStatus.DISMISSED:
                defect.resolved_at = now
                await self._reconcile_vehicle(
                    session=session,
                    organization_id=organization_id,
                    defect=defect,
                    actor_user_id=actor_user_id,
                    now=now,
                )
            after = {
                "status": next_status.value,
                "resolution_note": defect.resolution_note,
            }
            session.add_all(
                [
                    AuditEvent(
                        id=uuid.uuid4(),
                        organization_id=organization_id,
                        actor_user_id=actor_user_id,
                        action="defect.status_changed",
                        entity_type="defect",
                        entity_id=defect.id,
                        before_data=before,
                        after_data=after,
                        request_id=request_id,
                        created_at=now,
                    ),
                    self._event(defect, actor_user_id, request_id, now),
                    Notification(
                        id=uuid.uuid4(),
                        organization_id=organization_id,
                        recipient_user_id=defect.reported_by_user_id,
                        type="defect_status_changed",
                        title="Reported defect updated",
                        body=(
                            f"Your {DefectSeverity(defect.severity).value} defect is now "
                            f"{next_status.value}."
                        ),
                        entity_type="defect",
                        entity_id=defect.id,
                        created_at=now,
                    ),
                ]
            )
            return defect

    @staticmethod
    async def _has_active_work_order(
        session: AsyncSession, organization_id: uuid.UUID, defect_id: uuid.UUID
    ) -> bool:
        active = [
            status
            for status in WorkOrderStatus
            if status not in {WorkOrderStatus.CLOSED, WorkOrderStatus.CANCELLED}
        ]
        return bool(
            await session.scalar(
                select(func.count(WorkOrder.id)).where(
                    WorkOrder.organization_id == organization_id,
                    WorkOrder.source_defect_id == defect_id,
                    WorkOrder.status.in_(active),
                )
            )
        )

    @staticmethod
    async def _reconcile_vehicle(
        *,
        session: AsyncSession,
        organization_id: uuid.UUID,
        defect: Defect,
        actor_user_id: uuid.UUID,
        now: datetime,
    ) -> None:
        vehicle = cast(
            Vehicle | None,
            await session.scalar(
                select(Vehicle)
                .where(
                    Vehicle.organization_id == organization_id,
                    Vehicle.id == defect.vehicle_id,
                )
                .with_for_update()
            ),
        )
        if vehicle is None:
            return
        active_defects = int(
            await session.scalar(
                select(func.count(Defect.id)).where(
                    Defect.organization_id == organization_id,
                    Defect.vehicle_id == defect.vehicle_id,
                    Defect.id != defect.id,
                    Defect.status.in_(
                        [DefectStatus.OPEN, DefectStatus.TRIAGED, DefectStatus.IN_REPAIR]
                    ),
                )
            )
            or 0
        )
        active_orders = int(
            await session.scalar(
                select(func.count(WorkOrder.id)).where(
                    WorkOrder.organization_id == organization_id,
                    WorkOrder.vehicle_id == defect.vehicle_id,
                    WorkOrder.status.not_in([WorkOrderStatus.CLOSED, WorkOrderStatus.CANCELLED]),
                )
            )
            or 0
        )
        due_schedules = int(
            await session.scalar(
                select(func.count(MaintenanceSchedule.id)).where(
                    MaintenanceSchedule.organization_id == organization_id,
                    MaintenanceSchedule.vehicle_id == defect.vehicle_id,
                    MaintenanceSchedule.status.in_(
                        [MaintenanceScheduleStatus.DUE, MaintenanceScheduleStatus.OVERDUE]
                    ),
                )
            )
            or 0
        )
        next_status = (
            VehicleStatus.UNDER_REPAIR
            if active_orders
            else VehicleStatus.MAINTENANCE_DUE
            if active_defects or due_schedules
            else VehicleStatus.AVAILABLE
        )
        current_status = VehicleStatus(vehicle.status)
        if current_status is next_status:
            return
        vehicle.status = next_status
        vehicle.version += 1
        session.add(
            VehicleStatusHistory(
                id=uuid.uuid4(),
                organization_id=organization_id,
                vehicle_id=vehicle.id,
                from_status=current_status,
                to_status=next_status,
                reason_code="defect_dismissed",
                reason_reference_id=defect.id,
                changed_by_user_id=actor_user_id,
                created_at=now,
            )
        )

    @staticmethod
    def _event(
        defect: Defect,
        actor_user_id: uuid.UUID,
        request_id: uuid.UUID,
        now: datetime,
    ) -> OutboxEvent:
        event_id = uuid.uuid4()
        event_type = "defect.status_changed.v1"
        return OutboxEvent(
            id=event_id,
            organization_id=defect.organization_id,
            event_type=event_type,
            aggregate_type="defect",
            aggregate_id=defect.id,
            payload={
                "event_id": str(event_id),
                "event_type": event_type,
                "occurred_at": now.isoformat(),
                "organization_id": str(defect.organization_id),
                "aggregate": {"type": "defect", "id": str(defect.id)},
                "actor_user_id": str(actor_user_id),
                "correlation_id": str(request_id),
                "data": {
                    "vehicle_id": str(defect.vehicle_id),
                    "status": DefectStatus(defect.status).value,
                    "severity": DefectSeverity(defect.severity).value,
                },
            },
            occurred_at=now,
            attempts=0,
        )
