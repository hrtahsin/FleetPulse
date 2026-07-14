import uuid
from collections.abc import Sequence
from typing import cast

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fleetpulse.defects.exceptions import DefectNotFoundError
from fleetpulse.defects.models import Defect
from fleetpulse.defects.types import DefectSeverity, DefectStatus
from fleetpulse.shared.database import get_session_factory


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
