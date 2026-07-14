import uuid
from datetime import UTC, datetime
from decimal import Decimal

from fastapi.testclient import TestClient

from apps.api.main import app
from fleetpulse.auth.dependencies import get_auth_service
from fleetpulse.auth.exceptions import AuthenticationError
from fleetpulse.auth.roles import MembershipRole
from fleetpulse.auth.service import CurrentIdentity
from fleetpulse.vehicles.api import get_vehicle_service
from fleetpulse.vehicles.exceptions import OdometerRollbackError, VehicleNotFoundError
from fleetpulse.vehicles.models import Vehicle, VehicleStatusHistory
from fleetpulse.vehicles.service import CreateVehicle, VehiclePage
from fleetpulse.vehicles.status import VehicleStatus

ORGANIZATION_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")
OTHER_ORGANIZATION_VEHICLE_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
VEHICLE_ID = uuid.UUID("44444444-4444-4444-4444-444444444444")
NOW = datetime(2026, 7, 14, 12, tzinfo=UTC)


class FakeAuthService:
    def __init__(self, role: MembershipRole) -> None:
        self.role = role

    async def current_identity(self, access_token: str) -> CurrentIdentity:
        if access_token == "invalid":
            raise AuthenticationError
        return CurrentIdentity(
            user_id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
            email=f"{self.role.value}@example.com",
            display_name="Fleet User",
            membership_id=uuid.UUID("22222222-2222-2222-2222-222222222222"),
            organization_id=ORGANIZATION_ID,
            organization_name="Demo Fleet",
            organization_slug="demo-fleet",
            organization_timezone="America/St_Johns",
            default_currency="CAD",
            role=self.role,
        )


class FakeVehicleService:
    def __init__(self) -> None:
        self.last_organization_id: uuid.UUID | None = None

    async def list(
        self,
        *,
        organization_id: uuid.UUID,
        limit: int,
        cursor: str | None,
        status: VehicleStatus | None,
        query: str | None,
    ) -> VehiclePage:
        self.last_organization_id = organization_id
        return VehiclePage(items=[_vehicle()], next_cursor=None)

    async def get(self, *, organization_id: uuid.UUID, vehicle_id: uuid.UUID) -> Vehicle:
        self.last_organization_id = organization_id
        if vehicle_id == OTHER_ORGANIZATION_VEHICLE_ID:
            raise VehicleNotFoundError
        return _vehicle()

    async def create(
        self,
        *,
        organization_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        data: CreateVehicle,
    ) -> Vehicle:
        self.last_organization_id = organization_id
        return _vehicle(unit_number=data.unit_number)

    async def update(
        self,
        *,
        organization_id: uuid.UUID,
        vehicle_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        expected_version: int,
        changes: dict[str, object],
        status_reason: str | None,
    ) -> Vehicle:
        self.last_organization_id = organization_id
        if Decimal(str(changes.get("odometer_km", "42000.0"))) < Decimal("42000.0"):
            raise OdometerRollbackError
        return _vehicle(version=expected_version + 1)

    async def history(
        self, *, organization_id: uuid.UUID, vehicle_id: uuid.UUID, limit: int
    ) -> list[VehicleStatusHistory]:
        self.last_organization_id = organization_id
        return [
            VehicleStatusHistory(
                id=uuid.uuid4(),
                organization_id=organization_id,
                vehicle_id=vehicle_id,
                from_status=None,
                to_status=VehicleStatus.AVAILABLE,
                reason_code="vehicle_created",
                changed_by_user_id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
                created_at=NOW,
            )
        ]


def _vehicle(
    *, unit_number: str = "FP-101", version: int = 1, organization_id: uuid.UUID = ORGANIZATION_ID
) -> Vehicle:
    return Vehicle(
        id=VEHICLE_ID,
        organization_id=organization_id,
        unit_number=unit_number,
        vin="1FTFW1E50NFA00001",
        registration="NL-101",
        make="Ford",
        model="F-150",
        model_year=2022,
        fuel_type="gasoline",
        odometer_km=Decimal("42000.0"),
        status=VehicleStatus.AVAILABLE,
        version=version,
        created_at=NOW,
        updated_at=NOW,
    )


def _client(
    *, role: MembershipRole = MembershipRole.MANAGER
) -> tuple[TestClient, FakeVehicleService]:
    service = FakeVehicleService()
    app.dependency_overrides[get_auth_service] = lambda: FakeAuthService(role)
    app.dependency_overrides[get_vehicle_service] = lambda: service
    return TestClient(app), service


def _clear_overrides() -> None:
    app.dependency_overrides.clear()


def test_vehicle_list_requires_authentication() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/vehicles")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"


def test_driver_can_list_vehicles_using_server_derived_tenant() -> None:
    client, service = _client(role=MembershipRole.DRIVER)
    with client:
        response = client.get(
            "/api/v1/vehicles",
            headers={
                "Authorization": "Bearer valid",
                "X-Organization-ID": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
            },
        )
    _clear_overrides()

    assert response.status_code == 200
    assert response.json()["items"][0]["unit_number"] == "FP-101"
    assert service.last_organization_id == ORGANIZATION_ID


def test_driver_cannot_create_vehicle() -> None:
    client, _ = _client(role=MembershipRole.DRIVER)
    with client:
        response = client.post(
            "/api/v1/vehicles",
            headers={"Authorization": "Bearer valid"},
            json=_create_payload(),
        )
    _clear_overrides()

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_manager_can_create_vehicle() -> None:
    client, service = _client()
    with client:
        response = client.post(
            "/api/v1/vehicles",
            headers={"Authorization": "Bearer valid"},
            json=_create_payload(),
        )
    _clear_overrides()

    assert response.status_code == 201
    assert response.json()["unit_number"] == "FP-202"
    assert service.last_organization_id == ORGANIZATION_ID


def test_cross_tenant_vehicle_id_returns_not_found() -> None:
    client, _ = _client()
    with client:
        response = client.get(
            f"/api/v1/vehicles/{OTHER_ORGANIZATION_VEHICLE_ID}",
            headers={"Authorization": "Bearer valid"},
        )
    _clear_overrides()

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "VEHICLE_NOT_FOUND"


def test_lower_odometer_is_returned_as_safe_validation_error() -> None:
    client, _ = _client()
    with client:
        response = client.patch(
            f"/api/v1/vehicles/{VEHICLE_ID}",
            headers={"Authorization": "Bearer valid"},
            json={"version": 1, "odometer_km": "41000.0"},
        )
    _clear_overrides()

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "ODOMETER_ROLLBACK"


def _create_payload() -> dict[str, object]:
    return {
        "unit_number": "FP-202",
        "vin": "1FTFW1E50NFA00002",
        "registration": "NL-202",
        "make": "Ford",
        "model": "Transit",
        "model_year": 2024,
        "fuel_type": "gasoline",
        "odometer_km": "1200.0",
    }
