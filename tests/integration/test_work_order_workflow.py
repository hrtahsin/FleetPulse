import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fleetpulse.audit.models import AuditEvent
from fleetpulse.auth.models import OrganizationMembership, User
from fleetpulse.auth.roles import MembershipRole
from fleetpulse.defects.models import Defect
from fleetpulse.defects.types import DefectSeverity, DefectStatus
from fleetpulse.inspections.models import Inspection, InspectionTemplate
from fleetpulse.inspections.types import InspectionStatus
from fleetpulse.notifications.models import Notification
from fleetpulse.organizations.models import Organization
from fleetpulse.outbox.models import OutboxEvent
from fleetpulse.vehicles.models import Vehicle, VehicleStatusHistory
from fleetpulse.vehicles.status import VehicleStatus
from fleetpulse.work_orders.exceptions import (
    WorkOrderMechanicNotFoundError,
    WorkOrderNotFoundError,
    WorkOrderPermissionError,
    WorkOrderSourceConflictError,
    WorkOrderSourceNotFoundError,
    WorkOrderStaleVersionError,
)
from fleetpulse.work_orders.models import WorkOrder, WorkOrderCostItem, WorkOrderNote
from fleetpulse.work_orders.service import AddCostItem, CreateWorkOrder, WorkOrderService
from fleetpulse.work_orders.types import WorkOrderCostKind, WorkOrderPriority, WorkOrderStatus

NOW = datetime(2026, 7, 14, 12, 0, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class WorkOrderFixture:
    organization_id: uuid.UUID
    owner_user_id: uuid.UUID
    owner_membership_id: uuid.UUID
    mechanic_user_id: uuid.UUID
    mechanic_membership_id: uuid.UUID
    other_mechanic_membership_id: uuid.UUID
    vehicle_id: uuid.UUID
    defect_id: uuid.UUID


@pytest.mark.asyncio
async def test_complete_repair_lifecycle_reconciles_vehicle_and_source(
    auth_database: async_sessionmaker[AsyncSession],
) -> None:
    fixture = await _create_fixture(auth_database, "fleet-a")
    service = WorkOrderService(session_factory=auth_database, clock=lambda: NOW)
    order = await service.create(
        organization_id=fixture.organization_id,
        actor_user_id=fixture.owner_user_id,
        request_id=uuid.uuid4(),
        data=CreateWorkOrder(
            source_defect_id=fixture.defect_id,
            maintenance_schedule_id=None,
            title="Repair critical brake defect",
            description="Diagnose the warning and restore safe braking.",
            priority=WorkOrderPriority.CRITICAL,
            assigned_mechanic_membership_id=fixture.mechanic_membership_id,
            currency="CAD",
        ),
    )
    assert order.number == 1
    assert order.version == 1

    order = await _transition(
        service,
        fixture,
        order,
        MembershipRole.OWNER,
        fixture.owner_user_id,
        fixture.owner_membership_id,
        WorkOrderStatus.TRIAGED,
    )
    order = await _transition(
        service,
        fixture,
        order,
        MembershipRole.OWNER,
        fixture.owner_user_id,
        fixture.owner_membership_id,
        WorkOrderStatus.APPROVED,
    )
    order = await _transition(
        service,
        fixture,
        order,
        MembershipRole.MECHANIC,
        fixture.mechanic_user_id,
        fixture.mechanic_membership_id,
        WorkOrderStatus.IN_PROGRESS,
        "Confirmed brake warning and began diagnosis.",
    )

    note = await service.add_note(
        organization_id=fixture.organization_id,
        work_order_id=order.id,
        actor_user_id=fixture.mechanic_user_id,
        actor_membership_id=fixture.mechanic_membership_id,
        actor_role=MembershipRole.MECHANIC,
        request_id=uuid.uuid4(),
        body="Rear brake sensor failed continuity testing.",
    )
    assert note.body.startswith("Rear brake")

    labour, order = await service.add_cost_item(
        organization_id=fixture.organization_id,
        work_order_id=order.id,
        actor_user_id=fixture.mechanic_user_id,
        actor_membership_id=fixture.mechanic_membership_id,
        actor_role=MembershipRole.MECHANIC,
        request_id=uuid.uuid4(),
        expected_version=order.version,
        data=AddCostItem(
            kind=WorkOrderCostKind.LABOUR,
            description="Brake diagnosis and sensor replacement",
            quantity=Decimal("1.50"),
            unit_cost=Decimal("95.00"),
        ),
    )
    assert labour.quantity == Decimal("1.50")
    part, order = await service.add_cost_item(
        organization_id=fixture.organization_id,
        work_order_id=order.id,
        actor_user_id=fixture.mechanic_user_id,
        actor_membership_id=fixture.mechanic_membership_id,
        actor_role=MembershipRole.MECHANIC,
        request_id=uuid.uuid4(),
        expected_version=order.version,
        data=AddCostItem(
            kind=WorkOrderCostKind.PART,
            description="Rear brake sensor",
            quantity=Decimal("1.00"),
            unit_cost=Decimal("68.40"),
        ),
    )
    assert part.unit_cost == Decimal("68.40")

    order = await _transition(
        service,
        fixture,
        order,
        MembershipRole.MECHANIC,
        fixture.mechanic_user_id,
        fixture.mechanic_membership_id,
        WorkOrderStatus.COMPLETED,
        "Road test passed with no brake warning.",
    )
    with pytest.raises(WorkOrderPermissionError):
        await _transition(
            service,
            fixture,
            order,
            MembershipRole.MECHANIC,
            fixture.mechanic_user_id,
            fixture.mechanic_membership_id,
            WorkOrderStatus.VERIFIED,
            "Mechanic cannot self-verify.",
        )
    order = await _transition(
        service,
        fixture,
        order,
        MembershipRole.OWNER,
        fixture.owner_user_id,
        fixture.owner_membership_id,
        WorkOrderStatus.VERIFIED,
        "Manager verified the repair and return-to-service check.",
    )
    order = await _transition(
        service,
        fixture,
        order,
        MembershipRole.OWNER,
        fixture.owner_user_id,
        fixture.owner_membership_id,
        WorkOrderStatus.CLOSED,
    )

    async with auth_database() as session:
        stored_order = await session.get(WorkOrder, order.id)
        defect = await session.get(Defect, fixture.defect_id)
        vehicle = await session.get(Vehicle, fixture.vehicle_id)
        histories = await _count(session, VehicleStatusHistory)
        notes = await _count(session, WorkOrderNote)
        costs = await _count(session, WorkOrderCostItem)
        audits = await session.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.entity_type == "work_order")
        )
        events = await session.scalar(
            select(func.count())
            .select_from(OutboxEvent)
            .where(OutboxEvent.aggregate_type == "work_order")
        )
        notifications = await _count(session, Notification)

    assert stored_order is not None
    assert stored_order.status == WorkOrderStatus.CLOSED
    assert stored_order.labour_hours == Decimal("1.50")
    assert stored_order.labour_cost == Decimal("142.50")
    assert stored_order.parts_cost == Decimal("68.40")
    assert defect is not None and defect.status == DefectStatus.RESOLVED
    assert vehicle is not None and vehicle.status == VehicleStatus.AVAILABLE
    assert histories == 2
    assert notes == 4
    assert costs == 2
    assert audits == 10
    assert events == 7
    assert notifications >= 7


@pytest.mark.asyncio
async def test_stale_assignment_and_tenant_boundaries_are_enforced(
    auth_database: async_sessionmaker[AsyncSession],
) -> None:
    fleet_a = await _create_fixture(auth_database, "fleet-a")
    fleet_b = await _create_fixture(auth_database, "fleet-b")
    service = WorkOrderService(session_factory=auth_database, clock=lambda: NOW)

    with pytest.raises(WorkOrderSourceNotFoundError):
        await service.create(
            organization_id=fleet_b.organization_id,
            actor_user_id=fleet_b.owner_user_id,
            request_id=uuid.uuid4(),
            data=_create_data(fleet_a.defect_id, fleet_b.mechanic_membership_id),
        )
    with pytest.raises(WorkOrderMechanicNotFoundError):
        await service.create(
            organization_id=fleet_a.organization_id,
            actor_user_id=fleet_a.owner_user_id,
            request_id=uuid.uuid4(),
            data=_create_data(fleet_a.defect_id, fleet_b.mechanic_membership_id),
        )

    order = await service.create(
        organization_id=fleet_a.organization_id,
        actor_user_id=fleet_a.owner_user_id,
        request_id=uuid.uuid4(),
        data=_create_data(fleet_a.defect_id, fleet_a.mechanic_membership_id),
    )
    with pytest.raises(WorkOrderSourceConflictError):
        await service.create(
            organization_id=fleet_a.organization_id,
            actor_user_id=fleet_a.owner_user_id,
            request_id=uuid.uuid4(),
            data=_create_data(fleet_a.defect_id, fleet_a.mechanic_membership_id),
        )
    with pytest.raises(WorkOrderStaleVersionError):
        await service.transition(
            organization_id=fleet_a.organization_id,
            work_order_id=order.id,
            actor_user_id=fleet_a.owner_user_id,
            actor_membership_id=fleet_a.owner_membership_id,
            actor_role=MembershipRole.OWNER,
            request_id=uuid.uuid4(),
            expected_version=99,
            next_status=WorkOrderStatus.TRIAGED,
            note=None,
        )
    with pytest.raises(WorkOrderNotFoundError):
        await service.get(
            organization_id=fleet_a.organization_id,
            work_order_id=order.id,
            actor_role=MembershipRole.MECHANIC,
            actor_membership_id=fleet_a.other_mechanic_membership_id,
        )


@pytest.mark.asyncio
async def test_create_failure_rolls_back_source_and_side_effects(
    auth_database: async_sessionmaker[AsyncSession],
) -> None:
    fixture = await _create_fixture(auth_database, "fleet-a")

    def fail_before_commit() -> None:
        raise RuntimeError("injected work-order failure")

    service = WorkOrderService(
        session_factory=auth_database,
        clock=lambda: NOW,
        before_commit=fail_before_commit,
    )
    with pytest.raises(RuntimeError, match="injected work-order failure"):
        await service.create(
            organization_id=fixture.organization_id,
            actor_user_id=fixture.owner_user_id,
            request_id=uuid.uuid4(),
            data=_create_data(fixture.defect_id, fixture.mechanic_membership_id),
        )

    async with auth_database() as session:
        defect = await session.get(Defect, fixture.defect_id)
        assert defect is not None and defect.status == DefectStatus.OPEN
        assert await _count(session, WorkOrder) == 0
        assert await _count(session, Notification) == 0
        assert await _count(session, AuditEvent) == 0
        assert await _count(session, OutboxEvent) == 0


async def _transition(
    service: WorkOrderService,
    fixture: WorkOrderFixture,
    order: WorkOrder,
    role: MembershipRole,
    user_id: uuid.UUID,
    membership_id: uuid.UUID,
    status: WorkOrderStatus,
    note: str | None = None,
) -> WorkOrder:
    return await service.transition(
        organization_id=fixture.organization_id,
        work_order_id=order.id,
        actor_user_id=user_id,
        actor_membership_id=membership_id,
        actor_role=role,
        request_id=uuid.uuid4(),
        expected_version=order.version,
        next_status=status,
        note=note,
    )


def _create_data(defect_id: uuid.UUID, mechanic_id: uuid.UUID) -> CreateWorkOrder:
    return CreateWorkOrder(
        source_defect_id=defect_id,
        maintenance_schedule_id=None,
        title="Repair critical brake defect",
        description="Diagnose the warning and restore safe braking.",
        priority=WorkOrderPriority.CRITICAL,
        assigned_mechanic_membership_id=mechanic_id,
        currency="CAD",
    )


async def _count(session: AsyncSession, model: type[object]) -> int:
    return int(await session.scalar(select(func.count()).select_from(model)) or 0)


async def _create_fixture(factory: async_sessionmaker[AsyncSession], slug: str) -> WorkOrderFixture:
    organization_id = uuid.uuid4()
    owner_user_id = uuid.uuid4()
    owner_membership_id = uuid.uuid4()
    mechanic_user_id = uuid.uuid4()
    mechanic_membership_id = uuid.uuid4()
    other_mechanic_user_id = uuid.uuid4()
    other_mechanic_membership_id = uuid.uuid4()
    driver_user_id = uuid.uuid4()
    driver_membership_id = uuid.uuid4()
    vehicle_id = uuid.uuid4()
    template_id = uuid.uuid4()
    inspection_id = uuid.uuid4()
    defect_id = uuid.uuid4()
    async with factory() as session, session.begin():
        session.add(
            Organization(
                id=organization_id,
                name=f"Work orders {slug}",
                slug=f"work-orders-{slug}",
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
                    id=mechanic_user_id,
                    email=f"mechanic@{slug}.example.com",
                    password_hash="not-used",
                    display_name="Mechanic",
                    is_active=True,
                ),
                User(
                    id=other_mechanic_user_id,
                    email=f"mechanic-two@{slug}.example.com",
                    password_hash="not-used",
                    display_name="Other mechanic",
                    is_active=True,
                ),
                User(
                    id=driver_user_id,
                    email=f"driver@{slug}.example.com",
                    password_hash="not-used",
                    display_name="Driver",
                    is_active=True,
                ),
            ]
        )
        await session.flush()
        session.add_all(
            [
                OrganizationMembership(
                    id=owner_membership_id,
                    organization_id=organization_id,
                    user_id=owner_user_id,
                    role=MembershipRole.OWNER,
                ),
                OrganizationMembership(
                    id=mechanic_membership_id,
                    organization_id=organization_id,
                    user_id=mechanic_user_id,
                    role=MembershipRole.MECHANIC,
                ),
                OrganizationMembership(
                    id=other_mechanic_membership_id,
                    organization_id=organization_id,
                    user_id=other_mechanic_user_id,
                    role=MembershipRole.MECHANIC,
                ),
                OrganizationMembership(
                    id=driver_membership_id,
                    organization_id=organization_id,
                    user_id=driver_user_id,
                    role=MembershipRole.DRIVER,
                ),
                Vehicle(
                    id=vehicle_id,
                    organization_id=organization_id,
                    unit_number=f"{slug}-101",
                    make="Ford",
                    model="Transit",
                    model_year=2024,
                    odometer_km=Decimal("42000.0"),
                    status=VehicleStatus.OUT_OF_SERVICE,
                    version=1,
                    created_at=NOW,
                    updated_at=NOW,
                ),
                InspectionTemplate(
                    id=template_id,
                    organization_id=organization_id,
                    name="Pre-shift",
                    version=1,
                    is_active=True,
                    created_at=NOW,
                    updated_at=NOW,
                ),
            ]
        )
        await session.flush()
        session.add(
            Inspection(
                id=inspection_id,
                organization_id=organization_id,
                vehicle_id=vehicle_id,
                driver_membership_id=driver_membership_id,
                template_id=template_id,
                odometer_km=Decimal("42000.0"),
                status=InspectionStatus.SUBMITTED,
                submitted_at=NOW,
                created_at=NOW,
                idempotency_key=f"inspection-{slug}",
                request_hash="a" * 64,
            )
        )
        await session.flush()
        session.add(
            Defect(
                id=defect_id,
                organization_id=organization_id,
                inspection_id=inspection_id,
                inspection_response_id=None,
                vehicle_id=vehicle_id,
                category="brakes",
                description="Brake warning light remained on",
                severity=DefectSeverity.CRITICAL,
                status=DefectStatus.OPEN,
                reported_by_user_id=driver_user_id,
                created_at=NOW,
                updated_at=NOW,
            )
        )
    return WorkOrderFixture(
        organization_id=organization_id,
        owner_user_id=owner_user_id,
        owner_membership_id=owner_membership_id,
        mechanic_user_id=mechanic_user_id,
        mechanic_membership_id=mechanic_membership_id,
        other_mechanic_membership_id=other_mechanic_membership_id,
        vehicle_id=vehicle_id,
        defect_id=defect_id,
    )
