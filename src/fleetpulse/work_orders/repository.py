from collections.abc import Sequence
from typing import cast
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from fleetpulse.auth.models import OrganizationMembership, User
from fleetpulse.auth.roles import MANAGEMENT_ROLES, MembershipRole
from fleetpulse.defects.models import Defect
from fleetpulse.defects.types import DefectSeverity, DefectStatus
from fleetpulse.maintenance.models import MaintenanceSchedule
from fleetpulse.maintenance.types import MaintenanceScheduleStatus
from fleetpulse.organizations.models import Organization
from fleetpulse.vehicles.models import Vehicle
from fleetpulse.work_orders.models import WorkOrder, WorkOrderCostItem, WorkOrderNote
from fleetpulse.work_orders.types import WorkOrderStatus

TERMINAL_STATUSES = frozenset(
    {WorkOrderStatus.VERIFIED, WorkOrderStatus.CLOSED, WorkOrderStatus.CANCELLED}
)


class WorkOrderRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_orders(
        self,
        organization_id: UUID,
        *,
        status: WorkOrderStatus | None,
        assigned_membership_id: UUID | None,
        limit: int,
    ) -> Sequence[WorkOrder]:
        statement = select(WorkOrder).where(WorkOrder.organization_id == organization_id)
        if status is not None:
            statement = statement.where(WorkOrder.status == status)
        if assigned_membership_id is not None:
            statement = statement.where(
                WorkOrder.assigned_mechanic_membership_id == assigned_membership_id
            )
        statement = statement.order_by(WorkOrder.updated_at.desc(), WorkOrder.id.desc()).limit(
            limit
        )
        return (await self._session.scalars(statement)).all()

    async def get_order(
        self,
        organization_id: UUID,
        work_order_id: UUID,
        *,
        for_update: bool = False,
    ) -> WorkOrder | None:
        statement = select(WorkOrder).where(
            WorkOrder.organization_id == organization_id,
            WorkOrder.id == work_order_id,
        )
        if for_update:
            statement = statement.with_for_update()
        return cast(WorkOrder | None, await self._session.scalar(statement))

    async def get_defect(
        self, organization_id: UUID, defect_id: UUID, *, for_update: bool = False
    ) -> Defect | None:
        statement = select(Defect).where(
            Defect.organization_id == organization_id,
            Defect.id == defect_id,
        )
        if for_update:
            statement = statement.with_for_update()
        return cast(Defect | None, await self._session.scalar(statement))

    async def get_schedule(
        self, organization_id: UUID, schedule_id: UUID, *, for_update: bool = False
    ) -> MaintenanceSchedule | None:
        statement = select(MaintenanceSchedule).where(
            MaintenanceSchedule.organization_id == organization_id,
            MaintenanceSchedule.id == schedule_id,
        )
        if for_update:
            statement = statement.with_for_update()
        return cast(MaintenanceSchedule | None, await self._session.scalar(statement))

    async def get_vehicle(
        self, organization_id: UUID, vehicle_id: UUID, *, for_update: bool = False
    ) -> Vehicle | None:
        statement = select(Vehicle).where(
            Vehicle.organization_id == organization_id,
            Vehicle.id == vehicle_id,
        )
        if for_update:
            statement = statement.with_for_update()
        return cast(Vehicle | None, await self._session.scalar(statement))

    async def get_active_mechanic(
        self, organization_id: UUID, membership_id: UUID
    ) -> tuple[OrganizationMembership, User] | None:
        row = (
            await self._session.execute(
                select(OrganizationMembership, User)
                .join(User, User.id == OrganizationMembership.user_id)
                .where(
                    OrganizationMembership.organization_id == organization_id,
                    OrganizationMembership.id == membership_id,
                    OrganizationMembership.role == MembershipRole.MECHANIC,
                    User.is_active.is_(True),
                )
            )
        ).one_or_none()
        return (row[0], row[1]) if row is not None else None

    async def next_number(self, organization_id: UUID) -> int:
        await self._session.scalar(
            select(Organization.id).where(Organization.id == organization_id).with_for_update()
        )
        current = await self._session.scalar(
            select(func.max(WorkOrder.number)).where(WorkOrder.organization_id == organization_id)
        )
        return int(current or 0) + 1

    async def list_notes(
        self, organization_id: UUID, work_order_id: UUID
    ) -> Sequence[WorkOrderNote]:
        return (
            await self._session.scalars(
                select(WorkOrderNote)
                .where(
                    WorkOrderNote.organization_id == organization_id,
                    WorkOrderNote.work_order_id == work_order_id,
                )
                .order_by(WorkOrderNote.created_at, WorkOrderNote.id)
            )
        ).all()

    async def list_cost_items(
        self, organization_id: UUID, work_order_id: UUID
    ) -> Sequence[WorkOrderCostItem]:
        return (
            await self._session.scalars(
                select(WorkOrderCostItem)
                .where(
                    WorkOrderCostItem.organization_id == organization_id,
                    WorkOrderCostItem.work_order_id == work_order_id,
                )
                .order_by(WorkOrderCostItem.created_at, WorkOrderCostItem.id)
            )
        ).all()

    async def management_user_ids(self, organization_id: UUID) -> Sequence[UUID]:
        return (
            await self._session.scalars(
                select(User.id)
                .join(OrganizationMembership, OrganizationMembership.user_id == User.id)
                .where(
                    OrganizationMembership.organization_id == organization_id,
                    OrganizationMembership.role.in_([role.value for role in MANAGEMENT_ROLES]),
                    User.is_active.is_(True),
                )
            )
        ).all()

    async def mechanic_user_id(self, membership_id: UUID | None) -> UUID | None:
        if membership_id is None:
            return None
        return cast(
            UUID | None,
            await self._session.scalar(
                select(OrganizationMembership.user_id).where(
                    OrganizationMembership.id == membership_id
                )
            ),
        )

    async def has_active_other_order(
        self, organization_id: UUID, vehicle_id: UUID, exclude_id: UUID
    ) -> bool:
        return bool(
            await self._session.scalar(
                select(func.count())
                .select_from(WorkOrder)
                .where(
                    WorkOrder.organization_id == organization_id,
                    WorkOrder.vehicle_id == vehicle_id,
                    WorkOrder.id != exclude_id,
                    WorkOrder.status.not_in([status.value for status in TERMINAL_STATUSES]),
                )
            )
        )

    async def unresolved_defect_severities(
        self, organization_id: UUID, vehicle_id: UUID
    ) -> Sequence[DefectSeverity]:
        return (
            await self._session.scalars(
                select(Defect.severity).where(
                    Defect.organization_id == organization_id,
                    Defect.vehicle_id == vehicle_id,
                    Defect.status.in_(
                        [DefectStatus.OPEN, DefectStatus.TRIAGED, DefectStatus.IN_REPAIR]
                    ),
                )
            )
        ).all()

    async def has_due_schedule(self, organization_id: UUID, vehicle_id: UUID) -> bool:
        return bool(
            await self._session.scalar(
                select(func.count())
                .select_from(MaintenanceSchedule)
                .where(
                    MaintenanceSchedule.organization_id == organization_id,
                    MaintenanceSchedule.vehicle_id == vehicle_id,
                    MaintenanceSchedule.status.in_(
                        [MaintenanceScheduleStatus.DUE, MaintenanceScheduleStatus.OVERDUE]
                    ),
                )
            )
        )

    def add(self, *records: object) -> None:
        self._session.add_all(records)
