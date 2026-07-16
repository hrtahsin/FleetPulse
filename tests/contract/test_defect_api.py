from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from apps.api.main import app
from fleetpulse.auth.dependencies import get_auth_service
from fleetpulse.auth.exceptions import AuthenticationError
from fleetpulse.auth.roles import MembershipRole
from fleetpulse.auth.service import CurrentIdentity
from fleetpulse.defects.api import get_defect_service
from fleetpulse.defects.exceptions import (
    DefectHasActiveWorkOrderError,
    DefectNotFoundError,
    InvalidDefectTransitionError,
)
from fleetpulse.defects.models import Defect
from fleetpulse.defects.types import DefectSeverity, DefectStatus

ORGANIZATION_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")
USER_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
MEMBERSHIP_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
DEFECT_ID = uuid.UUID("77777777-7777-7777-7777-777777777777")
VEHICLE_ID = uuid.UUID("44444444-4444-4444-4444-444444444444")
INSPECTION_ID = uuid.UUID("55555555-5555-5555-5555-555555555555")
NOW = datetime(2026, 7, 14, 15, 30, tzinfo=UTC)


class FakeAuthService:
    def __init__(self, role: MembershipRole) -> None:
        self.role = role

    async def current_identity(self, access_token: str) -> CurrentIdentity:
        if access_token == "invalid":
            raise AuthenticationError
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


class FakeDefectService:
    def __init__(self) -> None:
        self.error: Exception | None = None
        self.last_update: tuple[uuid.UUID, uuid.UUID, DefectStatus, str | None] | None = None

    async def update_status(
        self,
        *,
        organization_id: uuid.UUID,
        defect_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        request_id: uuid.UUID,
        next_status: DefectStatus,
        resolution_note: str | None,
    ) -> Defect:
        if self.error is not None:
            raise self.error
        self.last_update = (organization_id, actor_user_id, next_status, resolution_note)
        return _defect(status=next_status, resolution_note=resolution_note)


def test_manager_can_triage_defect_in_authenticated_tenant() -> None:
    client, service = _client(MembershipRole.MANAGER)
    with client:
        response = client.patch(
            f"/api/v1/defects/{DEFECT_ID}",
            headers={"Authorization": "Bearer valid"},
            json={"status": "triaged", "resolution_note": "Parts review requested"},
        )
    _clear()

    assert response.status_code == 200
    assert response.json()["status"] == "triaged"
    assert service.last_update == (
        ORGANIZATION_ID,
        USER_ID,
        DefectStatus.TRIAGED,
        "Parts review requested",
    )


def test_mechanic_cannot_manage_defect_and_dismissal_requires_note() -> None:
    client, _ = _client(MembershipRole.MECHANIC)
    with client:
        forbidden = client.patch(
            f"/api/v1/defects/{DEFECT_ID}",
            headers={"Authorization": "Bearer valid"},
            json={"status": "triaged"},
        )
    _clear()

    client, _ = _client(MembershipRole.MANAGER)
    with client:
        invalid = client.patch(
            f"/api/v1/defects/{DEFECT_ID}",
            headers={"Authorization": "Bearer valid"},
            json={"status": "dismissed"},
        )
    _clear()

    assert forbidden.status_code == 403
    assert invalid.status_code == 422


def test_defect_management_errors_have_stable_codes() -> None:
    cases = [
        (DefectNotFoundError(), 404, "DEFECT_NOT_FOUND"),
        (InvalidDefectTransitionError(), 409, "INVALID_DEFECT_TRANSITION"),
        (DefectHasActiveWorkOrderError(), 409, "DEFECT_HAS_ACTIVE_WORK_ORDER"),
    ]
    for error, expected_status, expected_code in cases:
        client, service = _client(MembershipRole.OWNER)
        service.error = error
        with client:
            response = client.patch(
                f"/api/v1/defects/{DEFECT_ID}",
                headers={"Authorization": "Bearer valid"},
                json={"status": "triaged"},
            )
        _clear()
        assert response.status_code == expected_status
        assert response.json()["error"]["code"] == expected_code


def _client(role: MembershipRole) -> tuple[TestClient, FakeDefectService]:
    service = FakeDefectService()
    app.dependency_overrides[get_auth_service] = lambda: FakeAuthService(role)
    app.dependency_overrides[get_defect_service] = lambda: service
    return TestClient(app), service


def _clear() -> None:
    app.dependency_overrides.clear()


def _defect(*, status: DefectStatus, resolution_note: str | None) -> Defect:
    return Defect(
        id=DEFECT_ID,
        organization_id=ORGANIZATION_ID,
        inspection_id=INSPECTION_ID,
        inspection_response_id=None,
        vehicle_id=VEHICLE_ID,
        category="brakes",
        description="Brake warning light remained on",
        severity=DefectSeverity.CRITICAL,
        status=status,
        reported_by_user_id=USER_ID,
        resolved_at=NOW if status is DefectStatus.DISMISSED else None,
        resolution_note=resolution_note,
        created_at=NOW,
        updated_at=NOW,
    )
