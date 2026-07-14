import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from apps.api.main import app
from fleetpulse.auth.dependencies import get_auth_service
from fleetpulse.auth.exceptions import AuthenticationError
from fleetpulse.auth.roles import MembershipRole
from fleetpulse.auth.service import CurrentIdentity, TokenPair


class FakeAuthService:
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


def _token_pair() -> TokenPair:
    return TokenPair(
        access_token="access-token",
        refresh_token="refresh-token-with-at-least-thirty-two-characters",
        access_expires_at=datetime.now(UTC) + timedelta(minutes=15),
    )


def _client() -> TestClient:
    app.dependency_overrides[get_auth_service] = lambda: FakeAuthService()
    return TestClient(app)


def test_login_returns_access_and_refresh_tokens() -> None:
    with _client() as client:
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "manager@example.com", "password": "valid-password"},
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
