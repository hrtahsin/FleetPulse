import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fleetpulse.auth.models import OrganizationMembership, User
from fleetpulse.auth.roles import MembershipRole
from fleetpulse.organizations.models import Organization
from fleetpulse.vehicles.exceptions import (
    DuplicateVehicleError,
    OdometerRollbackError,
    StaleVehicleVersionError,
    VehicleNotFoundError,
)
from fleetpulse.vehicles.models import VehicleStatusHistory
from fleetpulse.vehicles.service import CreateVehicle, VehicleService
from fleetpulse.vehicles.status import VehicleStatus

NOW = datetime(2026, 7, 14, 12, tzinfo=UTC)


@pytest.mark.asyncio
async def test_vehicle_creation_records_history_and_rejects_duplicates(
    auth_database: async_sessionmaker[AsyncSession],
) -> None:
    organization_id, actor_id = await _create_tenant(auth_database, "fleet-a")
    service = _service(auth_database)

    vehicle = await service.create(
        organization_id=organization_id,
        actor_user_id=actor_id,
        data=_vehicle_data("FP-101", "1FTFW1E50NFA00101"),
    )

    with pytest.raises(DuplicateVehicleError):
        await service.create(
            organization_id=organization_id,
            actor_user_id=actor_id,
            data=_vehicle_data("FP-101", "1FTFW1E50NFA00999"),
        )

    async with auth_database() as session:
        history = await session.scalar(
            select(VehicleStatusHistory).where(VehicleStatusHistory.vehicle_id == vehicle.id)
        )
    assert history is not None
    assert history.from_status is None
    assert history.to_status == VehicleStatus.AVAILABLE
    assert history.changed_by_user_id == actor_id


@pytest.mark.asyncio
async def test_vehicle_reads_are_isolated_by_organization(
    auth_database: async_sessionmaker[AsyncSession],
) -> None:
    organization_a, actor_a = await _create_tenant(auth_database, "fleet-a")
    organization_b, _ = await _create_tenant(auth_database, "fleet-b")
    service = _service(auth_database)
    vehicle = await service.create(
        organization_id=organization_a,
        actor_user_id=actor_a,
        data=_vehicle_data("FP-101", "1FTFW1E50NFA00101"),
    )

    with pytest.raises(VehicleNotFoundError):
        await service.get(organization_id=organization_b, vehicle_id=vehicle.id)
    with pytest.raises(VehicleNotFoundError):
        await service.history(
            organization_id=organization_b,
            vehicle_id=vehicle.id,
            limit=50,
        )


@pytest.mark.asyncio
async def test_odometer_rollback_does_not_mutate_vehicle(
    auth_database: async_sessionmaker[AsyncSession],
) -> None:
    organization_id, actor_id = await _create_tenant(auth_database, "fleet-a")
    service = _service(auth_database)
    vehicle = await service.create(
        organization_id=organization_id,
        actor_user_id=actor_id,
        data=_vehicle_data("FP-101", "1FTFW1E50NFA00101"),
    )

    with pytest.raises(OdometerRollbackError):
        await service.update(
            organization_id=organization_id,
            vehicle_id=vehicle.id,
            actor_user_id=actor_id,
            expected_version=1,
            changes={"odometer_km": Decimal("999.9")},
            status_reason=None,
        )

    unchanged = await service.get(organization_id=organization_id, vehicle_id=vehicle.id)
    assert unchanged.odometer_km == Decimal("1000.0")
    assert unchanged.version == 1


@pytest.mark.asyncio
async def test_status_transition_is_versioned_and_audited(
    auth_database: async_sessionmaker[AsyncSession],
) -> None:
    organization_id, actor_id = await _create_tenant(auth_database, "fleet-a")
    service = _service(auth_database)
    vehicle = await service.create(
        organization_id=organization_id,
        actor_user_id=actor_id,
        data=_vehicle_data("FP-101", "1FTFW1E50NFA00101"),
    )

    updated = await service.update(
        organization_id=organization_id,
        vehicle_id=vehicle.id,
        actor_user_id=actor_id,
        expected_version=1,
        changes={"status": VehicleStatus.OUT_OF_SERVICE},
        status_reason="manager_safety_hold",
    )

    with pytest.raises(StaleVehicleVersionError):
        await service.update(
            organization_id=organization_id,
            vehicle_id=vehicle.id,
            actor_user_id=actor_id,
            expected_version=1,
            changes={"registration": "NL-NEW"},
            status_reason=None,
        )

    history = await service.history(
        organization_id=organization_id, vehicle_id=vehicle.id, limit=50
    )
    assert updated.status == VehicleStatus.OUT_OF_SERVICE
    assert updated.version == 2
    assert [record.reason_code for record in history] == [
        "manager_safety_hold",
        "vehicle_created",
    ]


@pytest.mark.asyncio
async def test_vehicle_pagination_returns_each_tenant_record_once(
    auth_database: async_sessionmaker[AsyncSession],
) -> None:
    organization_id, actor_id = await _create_tenant(auth_database, "fleet-a")
    service = _service(auth_database)
    for index in range(3):
        await service.create(
            organization_id=organization_id,
            actor_user_id=actor_id,
            data=_vehicle_data(f"FP-{index}", f"1FTFW1E50NFA00{index:03d}"),
        )

    first = await service.list(
        organization_id=organization_id,
        limit=2,
        cursor=None,
        status=None,
        query=None,
    )
    second = await service.list(
        organization_id=organization_id,
        limit=2,
        cursor=first.next_cursor,
        status=None,
        query=None,
    )

    ids = [vehicle.id for vehicle in [*first.items, *second.items]]
    assert len(ids) == 3
    assert len(set(ids)) == 3
    assert first.next_cursor is not None
    assert second.next_cursor is None


def _service(factory: async_sessionmaker[AsyncSession]) -> VehicleService:
    return VehicleService(session_factory=factory, clock=lambda: NOW)


def _vehicle_data(unit_number: str, vin: str) -> CreateVehicle:
    return CreateVehicle(
        unit_number=unit_number,
        vin=vin,
        registration=f"NL-{unit_number}",
        make="Ford",
        model="Transit",
        model_year=2024,
        fuel_type="gasoline",
        odometer_km=Decimal("1000.0"),
    )


async def _create_tenant(
    factory: async_sessionmaker[AsyncSession], slug: str
) -> tuple[uuid.UUID, uuid.UUID]:
    organization_id = uuid.uuid4()
    user_id = uuid.uuid4()
    async with factory() as session, session.begin():
        session.add(
            Organization(
                id=organization_id,
                name=f"Integration {slug}",
                slug=f"integration-{slug}",
                timezone="UTC",
                default_currency="CAD",
            )
        )
        session.add(
            User(
                id=user_id,
                email=f"manager@{slug}.example.com",
                password_hash="not-used-by-vehicle-tests",
                display_name="Integration Manager",
                is_active=True,
            )
        )
        await session.flush()
        session.add(
            OrganizationMembership(
                id=uuid.uuid4(),
                organization_id=organization_id,
                user_id=user_id,
                role=MembershipRole.MANAGER,
            )
        )
    return organization_id, user_id
