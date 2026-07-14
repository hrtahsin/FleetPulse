from collections.abc import Sequence
from typing import cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fleetpulse.auth.models import OrganizationMembership, User
from fleetpulse.auth.roles import MANAGEMENT_ROLES
from fleetpulse.maintenance.models import MaintenanceRule, MaintenanceSchedule
from fleetpulse.maintenance.types import MaintenanceScheduleStatus
from fleetpulse.vehicles.models import Vehicle
from fleetpulse.vehicles.status import VehicleStatus


class MaintenanceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_rules(self, organization_id: UUID) -> Sequence[MaintenanceRule]:
        return (
            await self._session.scalars(
                select(MaintenanceRule)
                .where(MaintenanceRule.organization_id == organization_id)
                .order_by(MaintenanceRule.active.desc(), MaintenanceRule.name, MaintenanceRule.id)
            )
        ).all()

    async def list_active_rules(self, organization_id: UUID) -> Sequence[MaintenanceRule]:
        return (
            await self._session.scalars(
                select(MaintenanceRule)
                .where(
                    MaintenanceRule.organization_id == organization_id,
                    MaintenanceRule.active.is_(True),
                )
                .order_by(MaintenanceRule.id)
            )
        ).all()

    async def get_rule(self, organization_id: UUID, rule_id: UUID) -> MaintenanceRule | None:
        return cast(
            MaintenanceRule | None,
            await self._session.scalar(
                select(MaintenanceRule).where(
                    MaintenanceRule.organization_id == organization_id,
                    MaintenanceRule.id == rule_id,
                )
            ),
        )

    async def get_vehicle(self, organization_id: UUID, vehicle_id: UUID) -> Vehicle | None:
        return cast(
            Vehicle | None,
            await self._session.scalar(
                select(Vehicle).where(
                    Vehicle.organization_id == organization_id,
                    Vehicle.id == vehicle_id,
                )
            ),
        )

    async def list_eligible_vehicles(self, organization_id: UUID) -> Sequence[Vehicle]:
        return (
            await self._session.scalars(
                select(Vehicle)
                .where(
                    Vehicle.organization_id == organization_id,
                    Vehicle.status != VehicleStatus.RETIRED,
                )
                .order_by(Vehicle.id)
            )
        ).all()

    async def list_schedules(
        self,
        organization_id: UUID,
        *,
        status: MaintenanceScheduleStatus | None = None,
    ) -> Sequence[MaintenanceSchedule]:
        statement = select(MaintenanceSchedule).where(
            MaintenanceSchedule.organization_id == organization_id
        )
        if status is not None:
            statement = statement.where(MaintenanceSchedule.status == status)
        statement = statement.order_by(
            MaintenanceSchedule.status,
            MaintenanceSchedule.due_at,
            MaintenanceSchedule.id,
        )
        return (await self._session.scalars(statement)).all()

    async def list_all_schedules(self, organization_id: UUID) -> Sequence[MaintenanceSchedule]:
        return (
            await self._session.scalars(
                select(MaintenanceSchedule).where(
                    MaintenanceSchedule.organization_id == organization_id
                )
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
                .order_by(User.id)
            )
        ).all()

    def add(self, *records: object) -> None:
        self._session.add_all(records)
