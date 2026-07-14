from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import delete, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from fleetpulse.auth.models import OrganizationMembership, RefreshToken, User
from fleetpulse.organizations.models import Organization
from fleetpulse.shared.config import get_settings


@pytest_asyncio.fixture
async def auth_database() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(get_settings().database_url, pool_pre_ping=True)
    try:
        async with engine.connect() as connection:
            has_schema = await connection.scalar(text("SELECT to_regclass('public.users')"))
            if has_schema is None:
                pytest.skip("identity database migration is not available")
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
        await session.execute(delete(RefreshToken))
        await session.execute(delete(OrganizationMembership))
        await session.execute(delete(User))
        await session.execute(delete(Organization))
