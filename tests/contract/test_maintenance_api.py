from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal

from fastapi.testclient import TestClient

from apps.api.main import app
from fleetpulse.auth.dependencies import get_auth_service
from fleetpulse.auth.roles import MembershipRole
from fleetpulse.auth.service import CurrentIdentity
from fleetpulse.maintenance.api import get_maintenance_service
from fleetpulse.maintenance.exceptions import MaintenanceVehicleNotFoundError
from fleetpulse.maintenance.models import MaintenanceRule, MaintenanceSchedule
from fleetpulse.maintenance.service import (
    CreateMaintenanceRule,
    EvaluationResult,
)
from fleetpulse.maintenance.types import MaintenanceScheduleStatus

ORGANIZATION_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")
USER_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
MEMBERSHIP_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
VEHICLE_ID = uuid.UUID("44444444-4444-4444-4444-444444444444")
MISSING_VEHICLE_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
RULE_ID = uuid.UUID("55555555-5555-5555-5555-555555555555")
SCHEDULE_ID = uuid.UUID("66666666-6666-6666-6666-666666666666")
NOW = datetime(2026, 7, 14, 12, 0, tzinfo=UTC)


class FakeAuthService:
    def __init__(self, role: MembershipRole) -> None:
        self.role = role

    async def current_identity(self, _: str) -> CurrentIdentity:
        return CurrentIdentity(
            user_id=USER_ID,
            email=f"{self.role.value}@example.com",
            display_name="Fleet User",
            membership_id=MEMBERSHIP_ID,
            organization_id=ORGANIZATION_ID,
            organization_name="Demo Fleet",
            organization_slug="demo-fleet",
            organization_timezone="America/St_Johns",
            default_currency="CAD",
            role=self.role,
        )


class FakeMaintenanceService:
    def __init__(self) -> None:
        self.last_organization_id: uuid.UUID | None = None

    async def list_rules(self, organization_id: uuid.UUID) -> Sequence[MaintenanceRule]:
        self.last_organization_id = organization_id
        return [_rule()]

    async def create_rule(
        self,
        *,
        organization_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        request_id: uuid.UUID,
        data: CreateMaintenanceRule,
    ) -> MaintenanceRule:
        self.last_organization_id = organization_id
        if data.vehicle_id == MISSING_VEHICLE_ID:
            raise MaintenanceVehicleNotFoundError
        return _rule(vehicle_id=data.vehicle_id)

    async def update_rule(
        self,
        *,
        organization_id: uuid.UUID,
        rule_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        request_id: uuid.UUID,
        changes: Mapping[str, object],
    ) -> MaintenanceRule:
        self.last_organization_id = organization_id
        return _rule()

    async def list_schedules(
        self,
        organization_id: uuid.UUID,
        *,
        status: MaintenanceScheduleStatus | None,
    ) -> Sequence[MaintenanceSchedule]:
        self.last_organization_id = organization_id
        return [_schedule()]

    async def evaluate(
        self,
        *,
        organization_id: uuid.UUID,
        actor_user_id: uuid.UUID | None,
        request_id: uuid.UUID,
    ) -> EvaluationResult:
        self.last_organization_id = organization_id
        return EvaluationResult(created=1, updated=0, due=1, overdue=0, schedules=[_schedule()])


def test_manager_creates_rule_with_server_derived_tenant() -> None:
    client, service = _client(MembershipRole.MANAGER)
    with client:
        response = client.post(
            "/api/v1/maintenance-rules",
            headers={"Authorization": "Bearer valid"},
            json={"name": "Oil service", "interval_km": "10000.0"},
        )
    _clear()

    assert response.status_code == 201
    assert response.json()["id"] == str(RULE_ID)
    assert service.last_organization_id == ORGANIZATION_ID


def test_cross_tenant_vehicle_reference_returns_not_found() -> None:
    client, _ = _client(MembershipRole.MANAGER)
    with client:
        response = client.post(
            "/api/v1/maintenance-rules",
            headers={"Authorization": "Bearer valid"},
            json={
                "name": "Vehicle-only service",
                "vehicle_id": str(MISSING_VEHICLE_ID),
                "interval_days": 90,
            },
        )
    _clear()

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "VEHICLE_NOT_FOUND"


def test_driver_is_forbidden_and_mechanic_can_read_schedules_only() -> None:
    driver, _ = _client(MembershipRole.DRIVER)
    with driver:
        driver_response = driver.get(
            "/api/v1/maintenance-schedules",
            headers={"Authorization": "Bearer valid"},
        )
    _clear()

    mechanic, _ = _client(MembershipRole.MECHANIC)
    with mechanic:
        schedules = mechanic.get(
            "/api/v1/maintenance-schedules",
            headers={"Authorization": "Bearer valid"},
        )
        rules = mechanic.get(
            "/api/v1/maintenance-rules",
            headers={"Authorization": "Bearer valid"},
        )
    _clear()

    assert driver_response.status_code == 403
    assert schedules.status_code == 200
    assert rules.status_code == 403


def test_manager_can_trigger_idempotent_evaluation() -> None:
    client, service = _client(MembershipRole.OWNER)
    with client:
        response = client.post(
            "/api/v1/maintenance-schedules/evaluate",
            headers={"Authorization": "Bearer valid"},
        )
    _clear()

    assert response.status_code == 200
    assert response.json()["created"] == 1
    assert response.json()["due"] == 1
    assert service.last_organization_id == ORGANIZATION_ID


def _client(role: MembershipRole) -> tuple[TestClient, FakeMaintenanceService]:
    service = FakeMaintenanceService()
    app.dependency_overrides[get_auth_service] = lambda: FakeAuthService(role)
    app.dependency_overrides[get_maintenance_service] = lambda: service
    return TestClient(app), service


def _clear() -> None:
    app.dependency_overrides.clear()


def _rule(vehicle_id: uuid.UUID | None = None) -> MaintenanceRule:
    return MaintenanceRule(
        id=RULE_ID,
        organization_id=ORGANIZATION_ID,
        name="Oil service",
        vehicle_id=vehicle_id,
        interval_km=Decimal("10000.0"),
        interval_days=None,
        active=True,
        created_at=NOW,
        updated_at=NOW,
    )


def _schedule() -> MaintenanceSchedule:
    return MaintenanceSchedule(
        id=SCHEDULE_ID,
        organization_id=ORGANIZATION_ID,
        vehicle_id=VEHICLE_ID,
        maintenance_rule_id=RULE_ID,
        due_at=NOW,
        due_odometer_km=Decimal("11000.0"),
        status=MaintenanceScheduleStatus.DUE,
        evaluated_at=NOW,
        created_at=NOW,
        updated_at=NOW,
    )
