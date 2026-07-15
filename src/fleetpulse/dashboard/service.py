import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.sql import Executable

from fleetpulse.dashboard.schemas import (
    DashboardSummaryResponse,
    DefectSummary,
    MaintenanceSummary,
    VehicleSummary,
    WorkOrderSummary,
)
from fleetpulse.defects.models import Defect
from fleetpulse.defects.types import DefectSeverity, DefectStatus
from fleetpulse.maintenance.models import MaintenanceSchedule
from fleetpulse.maintenance.types import MaintenanceScheduleStatus
from fleetpulse.shared.database import get_session_factory
from fleetpulse.vehicles.models import Vehicle
from fleetpulse.vehicles.status import VehicleStatus
from fleetpulse.work_orders.models import WorkOrder, WorkOrderCostItem
from fleetpulse.work_orders.types import WorkOrderStatus


class DashboardService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
    ) -> None:
        self._session_factory = session_factory or get_session_factory()

    async def summary(
        self, *, organization_id: uuid.UUID, currency: str
    ) -> DashboardSummaryResponse:
        now = datetime.now(UTC)
        async with self._session_factory() as session:
            vehicle_counts = await self._counts(
                session,
                select(Vehicle.status, func.count(Vehicle.id))
                .where(Vehicle.organization_id == organization_id)
                .group_by(Vehicle.status),
            )
            defect_counts = await self._counts(
                session,
                select(Defect.status, func.count(Defect.id))
                .where(Defect.organization_id == organization_id)
                .group_by(Defect.status),
            )
            maintenance_counts = await self._counts(
                session,
                select(MaintenanceSchedule.status, func.count(MaintenanceSchedule.id))
                .where(MaintenanceSchedule.organization_id == organization_id)
                .group_by(MaintenanceSchedule.status),
            )
            work_order_counts = await self._counts(
                session,
                select(WorkOrder.status, func.count(WorkOrder.id))
                .where(WorkOrder.organization_id == organization_id)
                .group_by(WorkOrder.status),
            )
            critical_defects = int(
                await session.scalar(
                    select(func.count(Defect.id)).where(
                        Defect.organization_id == organization_id,
                        Defect.severity == DefectSeverity.CRITICAL,
                        Defect.status.in_(
                            [
                                DefectStatus.OPEN,
                                DefectStatus.TRIAGED,
                                DefectStatus.IN_REPAIR,
                            ]
                        ),
                    )
                )
                or 0
            )
            active_work_order_statuses = [
                status
                for status in WorkOrderStatus
                if status not in {WorkOrderStatus.CLOSED, WorkOrderStatus.CANCELLED}
            ]
            unassigned = int(
                await session.scalar(
                    select(func.count(WorkOrder.id)).where(
                        WorkOrder.organization_id == organization_id,
                        WorkOrder.status.in_(active_work_order_statuses),
                        WorkOrder.assigned_mechanic_membership_id.is_(None),
                    )
                )
                or 0
            )
            repair_cost = await session.scalar(
                select(
                    func.coalesce(
                        func.sum(WorkOrderCostItem.quantity * WorkOrderCostItem.unit_cost),
                        0,
                    )
                )
                .join(WorkOrder, WorkOrder.id == WorkOrderCostItem.work_order_id)
                .where(
                    WorkOrder.organization_id == organization_id,
                    WorkOrderCostItem.created_at >= now - timedelta(days=30),
                )
            )

        total = sum(vehicle_counts.values())
        unavailable = sum(
            vehicle_counts.get(status.value, 0)
            for status in (
                VehicleStatus.UNDER_REPAIR,
                VehicleStatus.OUT_OF_SERVICE,
                VehicleStatus.RETIRED,
            )
        )
        active_defect_statuses = (
            DefectStatus.OPEN,
            DefectStatus.TRIAGED,
            DefectStatus.IN_REPAIR,
        )
        active_work_orders = sum(
            work_order_counts.get(status.value, 0) for status in active_work_order_statuses
        )
        return DashboardSummaryResponse(
            generated_at=now,
            currency=currency,
            vehicles=VehicleSummary(
                total=total,
                operational=total - unavailable,
                unavailable=unavailable,
                **{status.value: vehicle_counts.get(status.value, 0) for status in VehicleStatus},
            ),
            defects=DefectSummary(
                active=sum(defect_counts.get(status.value, 0) for status in active_defect_statuses),
                critical=critical_defects,
                triaged=defect_counts.get(DefectStatus.TRIAGED.value, 0),
                in_repair=defect_counts.get(DefectStatus.IN_REPAIR.value, 0),
            ),
            maintenance=MaintenanceSummary(
                upcoming=maintenance_counts.get(MaintenanceScheduleStatus.UPCOMING.value, 0),
                due=maintenance_counts.get(MaintenanceScheduleStatus.DUE.value, 0),
                overdue=maintenance_counts.get(MaintenanceScheduleStatus.OVERDUE.value, 0),
            ),
            work_orders=WorkOrderSummary(
                active=active_work_orders,
                unassigned=unassigned,
                waiting_parts=work_order_counts.get(WorkOrderStatus.WAITING_PARTS.value, 0),
                awaiting_verification=work_order_counts.get(WorkOrderStatus.COMPLETED.value, 0),
                repair_cost_30_days=Decimal(repair_cost or 0).quantize(Decimal("0.01")),
            ),
        )

    @staticmethod
    async def _counts(session: AsyncSession, statement: Executable) -> dict[str, int]:
        rows = (await session.execute(statement)).all()
        return {str(getattr(key, "value", key)): int(value) for key, value in rows}
