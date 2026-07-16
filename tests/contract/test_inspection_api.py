from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal

from fastapi.testclient import TestClient

from apps.api.main import app
from fleetpulse.auth.dependencies import get_auth_service
from fleetpulse.auth.exceptions import AuthenticationError
from fleetpulse.auth.roles import MembershipRole
from fleetpulse.auth.service import CurrentIdentity
from fleetpulse.inspections.api import get_inspection_service
from fleetpulse.inspections.exceptions import IdempotencyPayloadMismatchError
from fleetpulse.inspections.models import (
    Inspection,
    InspectionResponse,
    InspectionTemplate,
    InspectionTemplateItem,
)
from fleetpulse.inspections.service import (
    ActiveTemplate,
    InspectionDetails,
    SubmitInspection,
)
from fleetpulse.inspections.types import InspectionStatus, ResponseType
from fleetpulse.notifications.api import get_notification_service
from fleetpulse.notifications.models import Notification

ORGANIZATION_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")
USER_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
MEMBERSHIP_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
OTHER_MEMBERSHIP_ID = uuid.UUID("99999999-9999-9999-9999-999999999999")
VEHICLE_ID = uuid.UUID("44444444-4444-4444-4444-444444444444")
TEMPLATE_ID = uuid.UUID("55555555-5555-5555-5555-555555555555")
ITEM_ID = uuid.UUID("66666666-6666-6666-6666-666666666666")
INSPECTION_ID = uuid.UUID("77777777-7777-7777-7777-777777777777")
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


class FakeInspectionService:
    def __init__(self) -> None:
        self.last_organization_id: uuid.UUID | None = None
        self.last_driver_membership_id: uuid.UUID | None = None

    async def active_template(self, organization_id: uuid.UUID) -> ActiveTemplate:
        self.last_organization_id = organization_id
        return ActiveTemplate(template=_template(), items=[_template_item()])

    async def submit(
        self,
        *,
        organization_id: uuid.UUID,
        driver_membership_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        idempotency_key: str,
        request_id: uuid.UUID,
        submission: SubmitInspection,
    ) -> InspectionDetails:
        self.last_organization_id = organization_id
        self.last_driver_membership_id = driver_membership_id
        if idempotency_key == "mismatch-key":
            raise IdempotencyPayloadMismatchError
        return _details(replayed=idempotency_key == "replay-key")

    async def list(
        self,
        *,
        organization_id: uuid.UUID,
        driver_membership_id: uuid.UUID | None,
        limit: int,
    ) -> Sequence[Inspection]:
        self.last_organization_id = organization_id
        self.last_driver_membership_id = driver_membership_id
        return [_inspection()]

    async def get(
        self, *, organization_id: uuid.UUID, inspection_id: uuid.UUID
    ) -> InspectionDetails:
        self.last_organization_id = organization_id
        membership_id = OTHER_MEMBERSHIP_ID if inspection_id != INSPECTION_ID else MEMBERSHIP_ID
        return _details(driver_membership_id=membership_id)


class FakeNotificationService:
    def __init__(self) -> None:
        self.last_scope: tuple[uuid.UUID, uuid.UUID] | None = None
        self.marked_all_scope: tuple[uuid.UUID, uuid.UUID] | None = None

    async def list(
        self,
        *,
        organization_id: uuid.UUID,
        recipient_user_id: uuid.UUID,
        unread_only: bool,
        limit: int,
    ) -> Sequence[Notification]:
        self.last_scope = (organization_id, recipient_user_id)
        return []

    async def unread_count(
        self, *, organization_id: uuid.UUID, recipient_user_id: uuid.UUID
    ) -> int:
        self.last_scope = (organization_id, recipient_user_id)
        return 3

    async def mark_all_read(
        self, *, organization_id: uuid.UUID, recipient_user_id: uuid.UUID
    ) -> int:
        self.marked_all_scope = (organization_id, recipient_user_id)
        return 3


def test_inspection_submission_requires_authentication_and_idempotency_key() -> None:
    with TestClient(app) as client:
        unauthenticated = client.post("/api/v1/inspections", json=_payload())
    assert unauthenticated.status_code == 401

    client, _ = _client(MembershipRole.DRIVER)
    with client:
        missing_key = client.post(
            "/api/v1/inspections",
            headers={"Authorization": "Bearer valid"},
            json=_payload(),
        )
    _clear()
    assert missing_key.status_code == 422


def test_only_driver_can_submit_inspection() -> None:
    client, _ = _client(MembershipRole.MANAGER)
    with client:
        response = client.post(
            "/api/v1/inspections",
            headers={
                "Authorization": "Bearer valid",
                "Idempotency-Key": "manager-attempt",
            },
            json=_payload(),
        )
    _clear()

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_driver_submission_uses_server_derived_tenant_and_membership() -> None:
    client, service = _client(MembershipRole.DRIVER)
    with client:
        response = client.post(
            "/api/v1/inspections",
            headers={
                "Authorization": "Bearer valid",
                "Idempotency-Key": "driver-submission",
                "X-Organization-ID": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            },
            json=_payload(),
        )
    _clear()

    assert response.status_code == 201
    assert response.json()["id"] == str(INSPECTION_ID)
    assert service.last_organization_id == ORGANIZATION_ID
    assert service.last_driver_membership_id == MEMBERSHIP_ID


def test_replay_returns_ok_and_changed_payload_returns_conflict() -> None:
    client, _ = _client(MembershipRole.DRIVER)
    with client:
        replay = client.post(
            "/api/v1/inspections",
            headers={"Authorization": "Bearer valid", "Idempotency-Key": "replay-key"},
            json=_payload(),
        )
        mismatch = client.post(
            "/api/v1/inspections",
            headers={
                "Authorization": "Bearer valid",
                "Idempotency-Key": "mismatch-key",
            },
            json=_payload(),
        )
    _clear()

    assert replay.status_code == 200
    assert replay.json()["replayed"] is True
    assert mismatch.status_code == 409
    assert mismatch.json()["error"]["code"] == "IDEMPOTENCY_PAYLOAD_MISMATCH"


def test_driver_cannot_read_another_drivers_inspection() -> None:
    client, _ = _client(MembershipRole.DRIVER)
    with client:
        response = client.get(
            f"/api/v1/inspections/{uuid.uuid4()}",
            headers={"Authorization": "Bearer valid"},
        )
    _clear()

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "INSPECTION_NOT_FOUND"


def test_driver_cannot_list_defects() -> None:
    client, _ = _client(MembershipRole.DRIVER)
    with client:
        response = client.get("/api/v1/defects", headers={"Authorization": "Bearer valid"})
    _clear()

    assert response.status_code == 403


def test_notifications_are_scoped_to_authenticated_recipient() -> None:
    inspection_service = FakeInspectionService()
    notification_service = FakeNotificationService()
    app.dependency_overrides[get_auth_service] = lambda: FakeAuthService(MembershipRole.MANAGER)
    app.dependency_overrides[get_inspection_service] = lambda: inspection_service
    app.dependency_overrides[get_notification_service] = lambda: notification_service
    with TestClient(app) as client:
        response = client.get("/api/v1/notifications", headers={"Authorization": "Bearer valid"})
    _clear()

    assert response.status_code == 200
    assert response.json()["unread_count"] == 3
    assert notification_service.last_scope == (ORGANIZATION_ID, USER_ID)


def test_notifications_can_be_marked_read_in_authenticated_scope() -> None:
    notification_service = FakeNotificationService()
    app.dependency_overrides[get_auth_service] = lambda: FakeAuthService(MembershipRole.MANAGER)
    app.dependency_overrides[get_notification_service] = lambda: notification_service
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/notifications/read-all", headers={"Authorization": "Bearer valid"}
        )
    _clear()

    assert response.status_code == 200
    assert response.json() == {"updated": 3}
    assert notification_service.marked_all_scope == (ORGANIZATION_ID, USER_ID)


def _client(role: MembershipRole) -> tuple[TestClient, FakeInspectionService]:
    service = FakeInspectionService()
    app.dependency_overrides[get_auth_service] = lambda: FakeAuthService(role)
    app.dependency_overrides[get_inspection_service] = lambda: service
    return TestClient(app), service


def _clear() -> None:
    app.dependency_overrides.clear()


def _template() -> InspectionTemplate:
    return InspectionTemplate(
        id=TEMPLATE_ID,
        organization_id=ORGANIZATION_ID,
        name="Pre-shift",
        version=1,
        is_active=True,
        created_at=NOW,
        updated_at=NOW,
    )


def _template_item() -> InspectionTemplateItem:
    return InspectionTemplateItem(
        id=ITEM_ID,
        template_id=TEMPLATE_ID,
        code="service_brakes",
        label="Service brakes respond normally",
        category="brakes",
        response_type=ResponseType.PASS_FAIL,
        required=True,
        sort_order=1,
    )


def _inspection(*, driver_membership_id: uuid.UUID = MEMBERSHIP_ID) -> Inspection:
    return Inspection(
        id=INSPECTION_ID,
        organization_id=ORGANIZATION_ID,
        vehicle_id=VEHICLE_ID,
        driver_membership_id=driver_membership_id,
        template_id=TEMPLATE_ID,
        odometer_km=Decimal("1000.0"),
        status=InspectionStatus.SUBMITTED,
        notes=None,
        submitted_at=NOW,
        created_at=NOW,
        idempotency_key="driver-submission",
        request_hash="0" * 64,
    )


def _details(
    *, replayed: bool = False, driver_membership_id: uuid.UUID = MEMBERSHIP_ID
) -> InspectionDetails:
    return InspectionDetails(
        inspection=_inspection(driver_membership_id=driver_membership_id),
        responses=[
            InspectionResponse(
                id=uuid.uuid4(),
                inspection_id=INSPECTION_ID,
                template_item_id=ITEM_ID,
                result="pass",
                comment=None,
            )
        ],
        defects=[],
        replayed=replayed,
    )


def _payload() -> dict[str, object]:
    return {
        "vehicle_id": str(VEHICLE_ID),
        "template_id": str(TEMPLATE_ID),
        "odometer_km": "1000.0",
        "notes": None,
        "responses": [{"template_item_id": str(ITEM_ID), "result": "pass"}],
    }
