from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import delete, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from fleetpulse.audit.models import AuditEvent
from fleetpulse.auth.models import OrganizationMembership, RefreshToken, User
from fleetpulse.defects.models import Defect
from fleetpulse.inspections.models import (
    Inspection,
    InspectionResponse,
    InspectionTemplate,
    InspectionTemplateItem,
)
from fleetpulse.maintenance.models import MaintenanceRule, MaintenanceSchedule
from fleetpulse.notifications.models import Notification
from fleetpulse.organizations.models import Organization
from fleetpulse.outbox.models import OutboxEvent
from fleetpulse.shared.config import get_settings
from fleetpulse.vehicles.models import Vehicle, VehicleAssignment, VehicleStatusHistory


@pytest_asyncio.fixture
async def auth_database() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(get_settings().database_url, pool_pre_ping=True)
    try:
        async with engine.connect() as connection:
            has_schema = await connection.scalar(
                text("SELECT to_regclass('public.maintenance_schedules')")
            )
            if has_schema is None:
                pytest.skip("current database migrations are not available")
    except (OSError, SQLAlchemyError):
        await engine.dispose()
        pytest.skip("PostgreSQL is not available")

    factory = async_sessionmaker(engine, expire_on_commit=False)
    await _clean(factory)
    try:
        yield factory
    finally:
        await _clean(factory)
        await engine.dispose()


async def _clean(factory: async_sessionmaker[AsyncSession]) -> None:
    async with factory() as session, session.begin():
        await session.execute(delete(OutboxEvent))
        await session.execute(delete(AuditEvent))
        await session.execute(delete(Notification))
        await session.execute(delete(MaintenanceSchedule))
        await session.execute(delete(MaintenanceRule))
        await session.execute(delete(Defect))
        await session.execute(delete(InspectionResponse))
        await session.execute(delete(Inspection))
        await session.execute(delete(InspectionTemplateItem))
        await session.execute(delete(InspectionTemplate))
        await session.execute(delete(VehicleStatusHistory))
        await session.execute(delete(VehicleAssignment))
        await session.execute(delete(Vehicle))
        await session.execute(delete(RefreshToken))
        await session.execute(delete(OrganizationMembership))
        await session.execute(delete(User))
        await session.execute(delete(Organization))
