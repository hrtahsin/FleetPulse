import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fleetpulse.audit.models import AuditEvent
from fleetpulse.audit.service import AuditService
from fleetpulse.auth.models import OrganizationMembership, User
from fleetpulse.auth.roles import MembershipRole
from fleetpulse.dashboard.service import DashboardService
from fleetpulse.defects.exceptions import DefectNotFoundError, InvalidDefectTransitionError
from fleetpulse.defects.models import Defect
from fleetpulse.defects.service import DefectService
from fleetpulse.defects.types import DefectSeverity, DefectStatus
from fleetpulse.inspections.exceptions import (
    IdempotencyPayloadMismatchError,
    InspectionNotFoundError,
)
from fleetpulse.inspections.models import (
    Inspection,
    InspectionResponse,
    InspectionTemplate,
    InspectionTemplateItem,
)
from fleetpulse.inspections.service import (
    InspectionService,
    ReportedDefect,
    SubmitInspection,
    SubmittedResponse,
)
from fleetpulse.inspections.types import ResponseType
from fleetpulse.notifications.models import Notification
from fleetpulse.notifications.service import NotificationService
from fleetpulse.organizations.models import Organization
from fleetpulse.outbox.models import OutboxEvent
from fleetpulse.vehicles.models import Vehicle, VehicleStatusHistory
from fleetpulse.vehicles.status import VehicleStatus

NOW = datetime(2026, 7, 14, 15, 30, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class SafetyFixture:
    organization_id: uuid.UUID
    manager_user_id: uuid.UUID
    driver_user_id: uuid.UUID
    driver_membership_id: uuid.UUID
    vehicle_id: uuid.UUID
    template_id: uuid.UUID
    brakes_item_id: uuid.UUID
    tires_item_id: uuid.UUID


@pytest.mark.asyncio
async def test_critical_defect_commits_complete_safety_workflow(
    auth_database: async_sessionmaker[AsyncSession],
) -> None:
    fixture = await _create_safety_fixture(auth_database, "fleet-a")
    service = InspectionService(session_factory=auth_database, clock=lambda: NOW)

    details = await service.submit(
        organization_id=fixture.organization_id,
        driver_membership_id=fixture.driver_membership_id,
        actor_user_id=fixture.driver_user_id,
        idempotency_key="critical-inspection-001",
        request_id=uuid.uuid4(),
        submission=_critical_submission(fixture),
    )

    async with auth_database() as session:
        vehicle = await session.get(Vehicle, fixture.vehicle_id)
        counts = {
            "inspections": await _count(session, Inspection),
            "responses": await _count(session, InspectionResponse),
            "defects": await _count(session, Defect),
            "history": await _count(session, VehicleStatusHistory),
            "notifications": await _count(session, Notification),
            "audit": await _count(session, AuditEvent),
            "outbox": await _count(session, OutboxEvent),
        }
        event_types = set((await session.scalars(select(OutboxEvent.event_type))).all())

    assert details.replayed is False
    assert len(details.defects) == 1
    assert vehicle is not None
    assert vehicle.status == VehicleStatus.OUT_OF_SERVICE
    assert vehicle.odometer_km == Decimal("1008.4")
    assert counts == {
        "inspections": 1,
        "responses": 2,
        "defects": 1,
        "history": 2,
        "notifications": 2,
        "audit": 3,
        "outbox": 3,
    }
    assert event_types == {
        "inspection.submitted.v1",
        "defect.critical_reported.v1",
        "vehicle.status_changed.v1",
    }


@pytest.mark.asyncio
async def test_identical_retry_replays_and_changed_payload_conflicts(
    auth_database: async_sessionmaker[AsyncSession],
) -> None:
    fixture = await _create_safety_fixture(auth_database, "fleet-a")
    service = InspectionService(session_factory=auth_database, clock=lambda: NOW)
    request_id = uuid.uuid4()
    submission = _all_pass_submission(fixture)

    original = await service.submit(
        organization_id=fixture.organization_id,
        driver_membership_id=fixture.driver_membership_id,
        actor_user_id=fixture.driver_user_id,
        idempotency_key="repeat-safe-inspection",
        request_id=request_id,
        submission=submission,
    )
    replay = await service.submit(
        organization_id=fixture.organization_id,
        driver_membership_id=fixture.driver_membership_id,
        actor_user_id=fixture.driver_user_id,
        idempotency_key="repeat-safe-inspection",
        request_id=uuid.uuid4(),
        submission=submission,
    )

    changed = SubmitInspection(
        vehicle_id=submission.vehicle_id,
        template_id=submission.template_id,
        odometer_km=Decimal("1010.0"),
        notes=submission.notes,
        responses=submission.responses,
    )
    with pytest.raises(IdempotencyPayloadMismatchError):
        await service.submit(
            organization_id=fixture.organization_id,
            driver_membership_id=fixture.driver_membership_id,
            actor_user_id=fixture.driver_user_id,
            idempotency_key="repeat-safe-inspection",
            request_id=uuid.uuid4(),
            submission=changed,
        )

    async with auth_database() as session:
        inspection_count = await _count(session, Inspection)
    assert replay.replayed is True
    assert replay.inspection.id == original.inspection.id
    assert inspection_count == 1


@pytest.mark.asyncio
async def test_failure_rolls_back_every_synchronous_change(
    auth_database: async_sessionmaker[AsyncSession],
) -> None:
    fixture = await _create_safety_fixture(auth_database, "fleet-a")

    def fail_before_commit() -> None:
        raise RuntimeError("injected transaction failure")

    service = InspectionService(
        session_factory=auth_database,
        clock=lambda: NOW,
        before_commit=fail_before_commit,
    )
    with pytest.raises(RuntimeError, match="injected transaction failure"):
        await service.submit(
            organization_id=fixture.organization_id,
            driver_membership_id=fixture.driver_membership_id,
            actor_user_id=fixture.driver_user_id,
            idempotency_key="rollback-inspection",
            request_id=uuid.uuid4(),
            submission=_critical_submission(fixture),
        )

    async with auth_database() as session:
        vehicle = await session.get(Vehicle, fixture.vehicle_id)
        assert await _count(session, Inspection) == 0
        assert await _count(session, Defect) == 0
        assert await _count(session, Notification) == 0
        assert await _count(session, AuditEvent) == 0
        assert await _count(session, OutboxEvent) == 0
    assert vehicle is not None
    assert vehicle.status == VehicleStatus.AVAILABLE
    assert vehicle.odometer_km == Decimal("1000.0")


@pytest.mark.asyncio
async def test_inspection_detail_is_tenant_isolated(
    auth_database: async_sessionmaker[AsyncSession],
) -> None:
    fleet_a = await _create_safety_fixture(auth_database, "fleet-a")
    fleet_b = await _create_safety_fixture(auth_database, "fleet-b")
    service = InspectionService(session_factory=auth_database, clock=lambda: NOW)
    details = await service.submit(
        organization_id=fleet_a.organization_id,
        driver_membership_id=fleet_a.driver_membership_id,
        actor_user_id=fleet_a.driver_user_id,
        idempotency_key="tenant-isolation-inspection",
        request_id=uuid.uuid4(),
        submission=_all_pass_submission(fleet_a),
    )

    with pytest.raises(InspectionNotFoundError):
        await service.get(
            organization_id=fleet_b.organization_id,
            inspection_id=details.inspection.id,
        )


@pytest.mark.asyncio
async def test_manager_safety_controls_dashboard_and_audit_are_tenant_isolated(
    auth_database: async_sessionmaker[AsyncSession],
) -> None:
    fleet_a = await _create_safety_fixture(auth_database, "fleet-a")
    fleet_b = await _create_safety_fixture(auth_database, "fleet-b")
    inspection_service = InspectionService(session_factory=auth_database, clock=lambda: NOW)
    submitted = await inspection_service.submit(
        organization_id=fleet_a.organization_id,
        driver_membership_id=fleet_a.driver_membership_id,
        actor_user_id=fleet_a.driver_user_id,
        idempotency_key="manager-safety-loop",
        request_id=uuid.uuid4(),
        submission=_critical_submission(fleet_a),
    )
    defect = submitted.defects[0]

    dashboard_service = DashboardService(session_factory=auth_database)
    fleet_a_summary = await dashboard_service.summary(
        organization_id=fleet_a.organization_id, currency="CAD"
    )
    fleet_b_summary = await dashboard_service.summary(
        organization_id=fleet_b.organization_id, currency="CAD"
    )

    assert fleet_a_summary.vehicles.total == 1
    assert fleet_a_summary.vehicles.unavailable == 1
    assert fleet_a_summary.defects.active == 1
    assert fleet_a_summary.defects.critical == 1
    assert fleet_b_summary.vehicles.total == 1
    assert fleet_b_summary.vehicles.unavailable == 0
    assert fleet_b_summary.defects.active == 0

    defect_service = DefectService(session_factory=auth_database)
    triaged = await defect_service.update_status(
        organization_id=fleet_a.organization_id,
        defect_id=defect.id,
        actor_user_id=fleet_a.manager_user_id,
        request_id=uuid.uuid4(),
        next_status=DefectStatus.TRIAGED,
        resolution_note="Reviewed by dispatch",
    )
    dismissed = await defect_service.update_status(
        organization_id=fleet_a.organization_id,
        defect_id=defect.id,
        actor_user_id=fleet_a.manager_user_id,
        request_id=uuid.uuid4(),
        next_status=DefectStatus.DISMISSED,
        resolution_note="Duplicate dashboard warning; brakes verified",
    )

    assert triaged.status == DefectStatus.TRIAGED
    assert dismissed.status == DefectStatus.DISMISSED
    assert dismissed.resolved_at is not None
    async with auth_database() as session:
        vehicle = await session.get(Vehicle, fleet_a.vehicle_id)
        status_events = list(
            (
                await session.scalars(
                    select(OutboxEvent).where(
                        OutboxEvent.organization_id == fleet_a.organization_id,
                        OutboxEvent.event_type == "defect.status_changed.v1",
                    )
                )
            ).all()
        )
    assert vehicle is not None
    assert vehicle.status == VehicleStatus.AVAILABLE
    assert len(status_events) == 2

    notification_service = NotificationService(session_factory=auth_database)
    assert (
        await notification_service.unread_count(
            organization_id=fleet_a.organization_id,
            recipient_user_id=fleet_a.driver_user_id,
        )
        == 2
    )
    assert (
        await notification_service.mark_all_read(
            organization_id=fleet_a.organization_id,
            recipient_user_id=fleet_a.driver_user_id,
        )
        == 2
    )
    assert (
        await notification_service.unread_count(
            organization_id=fleet_a.organization_id,
            recipient_user_id=fleet_a.driver_user_id,
        )
        == 0
    )

    audit_service = AuditService(session_factory=auth_database)
    fleet_a_events = await audit_service.list(
        organization_id=fleet_a.organization_id,
        entity_type="defect",
        entity_id=defect.id,
        action=None,
        actor_user_id=None,
        limit=50,
    )
    fleet_b_events = await audit_service.list(
        organization_id=fleet_b.organization_id,
        entity_type="defect",
        entity_id=defect.id,
        action=None,
        actor_user_id=None,
        limit=50,
    )
    assert [record.event.action for record in fleet_a_events].count(
        "defect.status_changed"
    ) == 2
    assert fleet_b_events == []

    with pytest.raises(DefectNotFoundError):
        await defect_service.update_status(
            organization_id=fleet_b.organization_id,
            defect_id=defect.id,
            actor_user_id=fleet_b.manager_user_id,
            request_id=uuid.uuid4(),
            next_status=DefectStatus.TRIAGED,
            resolution_note=None,
        )
    with pytest.raises(InvalidDefectTransitionError):
        await defect_service.update_status(
            organization_id=fleet_a.organization_id,
            defect_id=defect.id,
            actor_user_id=fleet_a.manager_user_id,
            request_id=uuid.uuid4(),
            next_status=DefectStatus.TRIAGED,
            resolution_note=None,
        )


async def _count(session: AsyncSession, model: type[object]) -> int:
    return int(await session.scalar(select(func.count()).select_from(model)) or 0)


def _critical_submission(fixture: SafetyFixture) -> SubmitInspection:
    return SubmitInspection(
        vehicle_id=fixture.vehicle_id,
        template_id=fixture.template_id,
        odometer_km=Decimal("1008.4"),
        notes="Brake warning light stayed on",
        responses=[
            SubmittedResponse(
                template_item_id=fixture.brakes_item_id,
                result="fail",
                comment="Warning light remained on",
                defect=ReportedDefect(
                    category="brakes",
                    description="Brake warning light remained on",
                    severity=DefectSeverity.CRITICAL,
                ),
            ),
            SubmittedResponse(template_item_id=fixture.tires_item_id, result="pass"),
        ],
    )


def _all_pass_submission(fixture: SafetyFixture) -> SubmitInspection:
    return SubmitInspection(
        vehicle_id=fixture.vehicle_id,
        template_id=fixture.template_id,
        odometer_km=Decimal("1008.4"),
        notes=None,
        responses=[
            SubmittedResponse(template_item_id=fixture.brakes_item_id, result="pass"),
            SubmittedResponse(template_item_id=fixture.tires_item_id, result="pass"),
        ],
    )


async def _create_safety_fixture(
    factory: async_sessionmaker[AsyncSession], slug: str
) -> SafetyFixture:
    organization_id = uuid.uuid4()
    vehicle_id = uuid.uuid4()
    template_id = uuid.uuid4()
    brakes_item_id = uuid.uuid4()
    tires_item_id = uuid.uuid4()
    users = {
        MembershipRole.OWNER: (uuid.uuid4(), uuid.uuid4()),
        MembershipRole.MANAGER: (uuid.uuid4(), uuid.uuid4()),
        MembershipRole.DRIVER: (uuid.uuid4(), uuid.uuid4()),
    }
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
        for role, (user_id, _) in users.items():
            session.add(
                User(
                    id=user_id,
                    email=f"{role.value}@{slug}.example.com",
                    password_hash="not-used-by-inspection-tests",
                    display_name=f"Integration {role.value}",
                    is_active=True,
                )
            )
        await session.flush()
        for role, (user_id, membership_id) in users.items():
            session.add(
                OrganizationMembership(
                    id=membership_id,
                    organization_id=organization_id,
                    user_id=user_id,
                    role=role,
                )
            )
        session.add(
            Vehicle(
                id=vehicle_id,
                organization_id=organization_id,
                unit_number=f"{slug}-101",
                vin=None,
                registration=None,
                make="Ford",
                model="Transit",
                model_year=2024,
                fuel_type="gasoline",
                odometer_km=Decimal("1000.0"),
                status=VehicleStatus.AVAILABLE,
                version=1,
            )
        )
        session.add(
            VehicleStatusHistory(
                id=uuid.uuid4(),
                organization_id=organization_id,
                vehicle_id=vehicle_id,
                from_status=None,
                to_status=VehicleStatus.AVAILABLE,
                reason_code="test_fixture",
                changed_by_user_id=users[MembershipRole.MANAGER][0],
                created_at=NOW,
            )
        )
        session.add(
            InspectionTemplate(
                id=template_id,
                organization_id=organization_id,
                name="Pre-shift",
                version=1,
                is_active=True,
            )
        )
        await session.flush()
        session.add_all(
            [
                InspectionTemplateItem(
                    id=brakes_item_id,
                    template_id=template_id,
                    code="service_brakes",
                    label="Service brakes respond normally",
                    category="brakes",
                    response_type=ResponseType.PASS_FAIL,
                    required=True,
                    sort_order=1,
                ),
                InspectionTemplateItem(
                    id=tires_item_id,
                    template_id=template_id,
                    code="tires",
                    label="Tires show no unsafe damage",
                    category="tires",
                    response_type=ResponseType.PASS_FAIL,
                    required=True,
                    sort_order=2,
                ),
            ]
        )
    driver_user_id, driver_membership_id = users[MembershipRole.DRIVER]
    return SafetyFixture(
        organization_id=organization_id,
        manager_user_id=users[MembershipRole.MANAGER][0],
        driver_user_id=driver_user_id,
        driver_membership_id=driver_membership_id,
        vehicle_id=vehicle_id,
        template_id=template_id,
        brakes_item_id=brakes_item_id,
        tires_item_id=tires_item_id,
    )
