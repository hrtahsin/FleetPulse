import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fleetpulse.audit.models import AuditEvent
from fleetpulse.auth.models import OrganizationMembership, User
from fleetpulse.auth.roles import MembershipRole
from fleetpulse.maintenance.exceptions import (
    MaintenanceRuleNotFoundError,
    MaintenanceVehicleNotFoundError,
)
from fleetpulse.maintenance.models import MaintenanceSchedule
from fleetpulse.maintenance.service import CreateMaintenanceRule, MaintenanceService
from fleetpulse.maintenance.types import MaintenanceScheduleStatus
from fleetpulse.notifications.models import Notification
from fleetpulse.organizations.models import Organization
from fleetpulse.outbox.models import OutboxEvent
from fleetpulse.vehicles.models import Vehicle
from fleetpulse.vehicles.status import VehicleStatus

NOW = datetime(2026, 7, 14, 12, 0, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class MaintenanceFixture:
    organization_id: uuid.UUID
    owner_user_id: uuid.UUID
    vehicle_id: uuid.UUID


@pytest.mark.asyncio
async def test_evaluation_is_idempotent_and_notifies_only_on_due_transition(
    auth_database: async_sessionmaker[AsyncSession],
) -> None:
    fixture = await _create_fixture(auth_database, "fleet-a", odometer=Decimal("12500.0"))
    service = MaintenanceService(session_factory=auth_database, clock=lambda: NOW)
    rule = await service.create_rule(
        organization_id=fixture.organization_id,
        actor_user_id=fixture.owner_user_id,
        request_id=uuid.uuid4(),
        data=CreateMaintenanceRule(
            name="Engine oil service",
            vehicle_id=None,
            interval_km=Decimal("10000.0"),
            interval_days=None,
        ),
    )

    first = await service.evaluate(
        organization_id=fixture.organization_id,
        actor_user_id=fixture.owner_user_id,
        request_id=uuid.uuid4(),
    )
    async with auth_database() as session, session.begin():
        vehicle = await session.get(Vehicle, fixture.vehicle_id)
        assert vehicle is not None
        vehicle.odometer_km = Decimal("23000.0")
    second = await service.evaluate(
        organization_id=fixture.organization_id,
        actor_user_id=fixture.owner_user_id,
        request_id=uuid.uuid4(),
    )
    third = await service.evaluate(
        organization_id=fixture.organization_id,
        actor_user_id=fixture.owner_user_id,
        request_id=uuid.uuid4(),
    )

    async with auth_database() as session:
        schedule = await session.scalar(select(MaintenanceSchedule))
        notifications = await _count(session, Notification)
        due_audits = await session.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.action == "maintenance.became_due")
        )
        due_events = await session.scalar(
            select(func.count())
            .select_from(OutboxEvent)
            .where(OutboxEvent.event_type == "maintenance.became_due.v1")
        )

    assert first.created == 1
    assert first.overdue == 0
    assert first.schedules[0].due_odometer_km == Decimal("22500.0")
    assert second.created == 0
    assert second.updated == 1
    assert second.overdue == 1
    assert third.created == 0
    assert third.updated == 1
    assert third.overdue == 1
    assert schedule is not None
    assert schedule.maintenance_rule_id == rule.id
    assert schedule.status == MaintenanceScheduleStatus.OVERDUE
    assert notifications == 2
    assert due_audits == 1
    assert due_events == 1


@pytest.mark.asyncio
async def test_rule_and_vehicle_references_are_tenant_isolated(
    auth_database: async_sessionmaker[AsyncSession],
) -> None:
    fleet_a = await _create_fixture(auth_database, "fleet-a", odometer=Decimal("1000.0"))
    fleet_b = await _create_fixture(auth_database, "fleet-b", odometer=Decimal("1000.0"))
    service = MaintenanceService(session_factory=auth_database, clock=lambda: NOW)
    rule = await service.create_rule(
        organization_id=fleet_a.organization_id,
        actor_user_id=fleet_a.owner_user_id,
        request_id=uuid.uuid4(),
        data=CreateMaintenanceRule(
            name="Annual inspection",
            vehicle_id=fleet_a.vehicle_id,
            interval_km=None,
            interval_days=365,
        ),
    )

    with pytest.raises(MaintenanceRuleNotFoundError):
        await service.update_rule(
            organization_id=fleet_b.organization_id,
            rule_id=rule.id,
            actor_user_id=fleet_b.owner_user_id,
            request_id=uuid.uuid4(),
            changes={"active": False},
        )
    with pytest.raises(MaintenanceVehicleNotFoundError):
        await service.create_rule(
            organization_id=fleet_b.organization_id,
            actor_user_id=fleet_b.owner_user_id,
            request_id=uuid.uuid4(),
            data=CreateMaintenanceRule(
                name="Cross-tenant attempt",
                vehicle_id=fleet_a.vehicle_id,
                interval_km=Decimal("5000.0"),
                interval_days=None,
            ),
        )


@pytest.mark.asyncio
async def test_evaluation_failure_rolls_back_schedule_and_side_effects(
    auth_database: async_sessionmaker[AsyncSession],
) -> None:
    fixture = await _create_fixture(auth_database, "fleet-a", odometer=Decimal("9000.0"))
    setup_service = MaintenanceService(session_factory=auth_database, clock=lambda: NOW)
    await setup_service.create_rule(
        organization_id=fixture.organization_id,
        actor_user_id=fixture.owner_user_id,
        request_id=uuid.uuid4(),
        data=CreateMaintenanceRule(
            name="Brake service",
            vehicle_id=None,
            interval_km=Decimal("8000.0"),
            interval_days=None,
        ),
    )

    def fail_before_commit() -> None:
        raise RuntimeError("injected maintenance failure")

    service = MaintenanceService(
        session_factory=auth_database,
        clock=lambda: NOW,
        before_commit=fail_before_commit,
    )
    with pytest.raises(RuntimeError, match="injected maintenance failure"):
        await service.evaluate(
            organization_id=fixture.organization_id,
            actor_user_id=fixture.owner_user_id,
            request_id=uuid.uuid4(),
        )

    async with auth_database() as session:
        assert await _count(session, MaintenanceSchedule) == 0
        assert await _count(session, Notification) == 0
        assert (
            await session.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(AuditEvent.action == "maintenance.became_due")
            )
            == 0
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(OutboxEvent)
                .where(OutboxEvent.event_type == "maintenance.became_due.v1")
            )
            == 0
        )


async def _count(session: AsyncSession, model: type[object]) -> int:
    return int(await session.scalar(select(func.count()).select_from(model)) or 0)


async def _create_fixture(
    factory: async_sessionmaker[AsyncSession],
    slug: str,
    *,
    odometer: Decimal,
) -> MaintenanceFixture:
    organization_id = uuid.uuid4()
    vehicle_id = uuid.uuid4()
    owner_user_id = uuid.uuid4()
    manager_user_id = uuid.uuid4()
    async with factory() as session, session.begin():
        session.add(
            Organization(
                id=organization_id,
                name=f"Maintenance {slug}",
                slug=f"maintenance-{slug}",
                timezone="UTC",
                default_currency="CAD",
            )
        )
        session.add_all(
            [
                User(
                    id=owner_user_id,
                    email=f"owner@{slug}.example.com",
                    password_hash="not-used",
                    display_name="Owner",
                    is_active=True,
                ),
                User(
                    id=manager_user_id,
                    email=f"manager@{slug}.example.com",
                    password_hash="not-used",
                    display_name="Manager",
                    is_active=True,
                ),
            ]
        )
        await session.flush()
        session.add_all(
            [
                OrganizationMembership(
                    id=uuid.uuid4(),
                    organization_id=organization_id,
                    user_id=owner_user_id,
                    role=MembershipRole.OWNER,
                ),
                OrganizationMembership(
                    id=uuid.uuid4(),
                    organization_id=organization_id,
                    user_id=manager_user_id,
                    role=MembershipRole.MANAGER,
                ),
                Vehicle(
                    id=vehicle_id,
                    organization_id=organization_id,
                    unit_number=f"{slug}-101",
                    make="Ford",
                    model="Transit",
                    model_year=2024,
                    odometer_km=odometer,
                    status=VehicleStatus.AVAILABLE,
                    version=1,
                    created_at=NOW - timedelta(days=100),
                    updated_at=NOW - timedelta(days=100),
                ),
            ]
        )
    return MaintenanceFixture(
        organization_id=organization_id,
        owner_user_id=owner_user_id,
        vehicle_id=vehicle_id,
    )
