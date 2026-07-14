from collections.abc import Sequence
from typing import cast
from uuid import UUID

from sqlalchemy import Select, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from fleetpulse.vehicles.models import Vehicle, VehicleStatusHistory
from fleetpulse.vehicles.status import VehicleStatus


class VehicleRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list(
        self,
        *,
        organization_id: UUID,
        limit: int,
        after_id: UUID | None = None,
        status: VehicleStatus | None = None,
        query: str | None = None,
    ) -> Sequence[Vehicle]:
        statement: Select[tuple[Vehicle]] = select(Vehicle).where(
            Vehicle.organization_id == organization_id
        )
        if after_id is not None:
            statement = statement.where(Vehicle.id > after_id)
        if status is not None:
            statement = statement.where(Vehicle.status == status)
        if query:
            pattern = f"%{query.strip()}%"
            statement = statement.where(
                or_(
                    Vehicle.unit_number.ilike(pattern),
                    Vehicle.vin.ilike(pattern),
                    Vehicle.registration.ilike(pattern),
                    Vehicle.make.ilike(pattern),
                    Vehicle.model.ilike(pattern),
                )
            )
        statement = statement.order_by(Vehicle.id).limit(limit)
        return (await self._session.scalars(statement)).all()

    async def get(
        self, organization_id: UUID, vehicle_id: UUID, *, for_update: bool = False
    ) -> Vehicle | None:
        statement = select(Vehicle).where(
            Vehicle.organization_id == organization_id,
            Vehicle.id == vehicle_id,
        )
        if for_update:
            statement = statement.with_for_update()
        return cast(Vehicle | None, await self._session.scalar(statement))

    async def has_identity_conflict(
        self,
        *,
        organization_id: UUID,
        unit_number: str,
        vin: str | None,
        exclude_vehicle_id: UUID | None = None,
    ) -> bool:
        identity_checks = [Vehicle.unit_number == unit_number]
        if vin is not None:
            identity_checks.append(Vehicle.vin == vin)
        statement = select(Vehicle.id).where(
            Vehicle.organization_id == organization_id,
            or_(*identity_checks),
        )
        if exclude_vehicle_id is not None:
            statement = statement.where(Vehicle.id != exclude_vehicle_id)
        return await self._session.scalar(statement.limit(1)) is not None

    async def list_history(
        self, *, organization_id: UUID, vehicle_id: UUID, limit: int
    ) -> Sequence[VehicleStatusHistory]:
        statement = (
            select(VehicleStatusHistory)
            .where(
                VehicleStatusHistory.organization_id == organization_id,
                VehicleStatusHistory.vehicle_id == vehicle_id,
            )
            .order_by(
                VehicleStatusHistory.created_at.desc(),
                VehicleStatusHistory.from_status.is_(None),
                VehicleStatusHistory.id.desc(),
            )
            .limit(limit)
        )
        return (await self._session.scalars(statement)).all()

    def add(self, record: Vehicle | VehicleStatusHistory) -> None:
        self._session.add(record)
