import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from apps.api.main import app
from fleetpulse.auth.dependencies import get_auth_service
from fleetpulse.auth.exceptions import AuthenticationError
from fleetpulse.auth.models import OrganizationMembership, User
from fleetpulse.auth.repository import MemberRecord
from fleetpulse.auth.roles import MembershipRole
from fleetpulse.auth.service import CreateMember, CurrentIdentity, TokenPair, UpdateMember


class FakeAuthService:
    def __init__(self) -> None:
        self.created: CreateMember | None = None
        self.updated: UpdateMember | None = None

    async def login(self, email: str, password: str, user_agent: str | None) -> TokenPair:
        if password == "incorrect-password":
            raise AuthenticationError
        return _token_pair()

    async def refresh(self, refresh_token: str, user_agent: str | None) -> TokenPair:
        if refresh_token.startswith("invalid"):
            raise AuthenticationError
        return _token_pair()

    async def logout(self, refresh_token: str) -> None:
        return None

    async def current_identity(self, access_token: str) -> CurrentIdentity:
        if access_token == "invalid":
            raise AuthenticationError
        return CurrentIdentity(
            user_id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
            email="manager@example.com",
            display_name="Demo Manager",
            membership_id=uuid.UUID("22222222-2222-2222-2222-222222222222"),
            organization_id=uuid.UUID("33333333-3333-3333-3333-333333333333"),
            organization_name="Demo Fleet",
            organization_slug="demo-fleet",
            organization_timezone="America/St_Johns",
            default_currency="CAD",
            role=MembershipRole.MANAGER,
        )

    async def list_members(
        self, organization_id: uuid.UUID, role: MembershipRole | None
    ) -> list[MemberRecord]:
        return [
            MemberRecord(
                membership=OrganizationMembership(
                    id=uuid.UUID("44444444-4444-4444-4444-444444444444"),
                    organization_id=organization_id,
                    user_id=uuid.UUID("55555555-5555-5555-5555-555555555555"),
                    role=role or MembershipRole.MECHANIC,
                ),
                user=User(
                    id=uuid.UUID("55555555-5555-5555-5555-555555555555"),
                    email="mechanic@example.com",
                    display_name="Demo Mechanic",
                    password_hash="not-used",
                    is_active=True,
                ),
            )
        ]

    async def create_member(self, *, data: CreateMember, **_: object) -> MemberRecord:
        self.created = data
        return _member_record(
            email=data.email,
            display_name=data.display_name,
            role=data.role,
        )

    async def update_member(self, *, data: UpdateMember, **_: object) -> MemberRecord:
        self.updated = data
        return _member_record(
            display_name=data.display_name or "Demo Mechanic",
            role=data.role or MembershipRole.MECHANIC,
            is_active=True if data.is_active is None else data.is_active,
        )


def _token_pair() -> TokenPair:
    return TokenPair(
        access_token="access-token",
        refresh_token="refresh-token-with-at-least-thirty-two-characters",
        access_expires_at=datetime.now(UTC) + timedelta(minutes=15),
    )


def _client() -> TestClient:
    app.dependency_overrides[get_auth_service] = lambda: FakeAuthService()
    return TestClient(app)


def _member_record(
    *,
    email: str = "mechanic@example.com",
    display_name: str = "Demo Mechanic",
    role: MembershipRole = MembershipRole.MECHANIC,
    is_active: bool = True,
) -> MemberRecord:
    return MemberRecord(
        membership=OrganizationMembership(
            id=uuid.UUID("44444444-4444-4444-4444-444444444444"),
            organization_id=uuid.UUID("33333333-3333-3333-3333-333333333333"),
            user_id=uuid.UUID("55555555-5555-5555-5555-555555555555"),
            role=role,
        ),
        user=User(
            id=uuid.UUID("55555555-5555-5555-5555-555555555555"),
            email=email,
            display_name=display_name,
            password_hash="not-used",
            is_active=is_active,
        ),
    )


def test_login_returns_access_and_refresh_tokens() -> None:
    with _client() as client:
        response = client.post(
            "/api/v1/auth/login",
            json={
                "email": "manager@demo.fleetpulse.example.com",
                "password": "valid-password",
            },
        )
    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["access_token"] == "access-token"
    assert response.json()["token_type"] == "bearer"
    assert uuid.UUID(response.headers["X-Request-ID"])


def test_login_failure_uses_safe_error_envelope() -> None:
    with _client() as client:
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "manager@example.com", "password": "incorrect-password"},
        )
    app.dependency_overrides.clear()

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTHENTICATION_FAILED"
    assert "incorrect-password" not in response.text


def test_validation_error_does_not_echo_password() -> None:
    with _client() as client:
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "not-an-email", "password": "secret-value"},
        )
    app.dependency_overrides.clear()

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert "secret-value" not in response.text


def test_me_requires_authentication() -> None:
    with _client() as client:
        response = client.get("/api/v1/me")
    app.dependency_overrides.clear()

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"


def test_me_returns_server_derived_tenant_context() -> None:
    with _client() as client:
        response = client.get(
            "/api/v1/me",
            headers={
                "Authorization": "Bearer valid",
                "X-Organization-ID": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            },
        )
    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["organization"]["id"] == "33333333-3333-3333-3333-333333333333"
    assert response.json()["role"] == "manager"


def test_manager_lists_mechanics_in_the_authenticated_tenant() -> None:
    with _client() as client:
        response = client.get(
            "/api/v1/members?role=mechanic",
            headers={"Authorization": "Bearer valid"},
        )
    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["items"] == [
        {
            "membership_id": "44444444-4444-4444-4444-444444444444",
            "user_id": "55555555-5555-5555-5555-555555555555",
            "email": "mechanic@example.com",
            "display_name": "Demo Mechanic",
            "role": "mechanic",
            "is_active": True,
        }
    ]


def test_manager_creates_driver_without_echoing_temporary_password() -> None:
    service = FakeAuthService()
    app.dependency_overrides[get_auth_service] = lambda: service
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/members",
            headers={"Authorization": "Bearer valid"},
            json={
                "email": "driver@example.com",
                "display_name": "Demo Driver",
                "role": "driver",
                "temporary_password": "temporary-password-123",
            },
        )
    app.dependency_overrides.clear()

    assert response.status_code == 201
    assert response.json()["role"] == "driver"
    assert "temporary-password-123" not in response.text
    assert service.created is not None
    assert service.created.email == "driver@example.com"


def test_owner_updates_member_role_and_activation() -> None:
    service = FakeAuthService()
    app.dependency_overrides[get_auth_service] = lambda: service
    with TestClient(app) as client:
        response = client.patch(
            "/api/v1/members/44444444-4444-4444-4444-444444444444",
            headers={"Authorization": "Bearer valid"},
            json={"role": "mechanic", "is_active": False},
        )
    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["is_active"] is False
    assert service.updated == UpdateMember(
        display_name=None,
        role=MembershipRole.MECHANIC,
        is_active=False,
    )
