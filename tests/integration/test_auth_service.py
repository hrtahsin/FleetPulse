import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fleetpulse.auth.exceptions import AuthenticationError, TokenReuseError
from fleetpulse.auth.models import OrganizationMembership, RefreshToken, User
from fleetpulse.auth.roles import MembershipRole
from fleetpulse.auth.security import PasswordSecurity
from fleetpulse.auth.service import AuthService
from fleetpulse.organizations.models import Organization
from fleetpulse.shared.config import Settings

NOW = datetime.now(UTC).replace(microsecond=0)


@pytest.mark.asyncio
async def test_login_rotation_and_reuse_detection_revoke_token_family(
    auth_database: async_sessionmaker[AsyncSession],
) -> None:
    await _create_identity(auth_database)
    service = _service(auth_database)

    first = await service.login("MANAGER@EXAMPLE.COM", "valid-demo-password", "integration-test")
    identity = await service.current_identity(first.access_token)
    replacement = await service.refresh(first.refresh_token, "integration-test")

    assert identity.role is MembershipRole.MANAGER
    assert identity.organization_slug == "integration-fleet"
    assert replacement.refresh_token != first.refresh_token

    with pytest.raises(TokenReuseError):
        await service.refresh(first.refresh_token, "integration-test")
    with pytest.raises(AuthenticationError):
        await service.refresh(replacement.refresh_token, "integration-test")

    async with auth_database() as session:
        token_count = await session.scalar(select(func.count()).select_from(RefreshToken))
        active_count = await session.scalar(
            select(func.count()).select_from(RefreshToken).where(RefreshToken.revoked_at.is_(None))
        )
    assert token_count == 2
    assert active_count == 0


@pytest.mark.asyncio
async def test_bad_password_and_logout_are_safe(
    auth_database: async_sessionmaker[AsyncSession],
) -> None:
    await _create_identity(auth_database)
    service = _service(auth_database)

    with pytest.raises(AuthenticationError):
        await service.login("manager@example.com", "wrong-password", None)

    tokens = await service.login("manager@example.com", "valid-demo-password", None)
    await service.logout(tokens.refresh_token)
    await service.logout(tokens.refresh_token)

    with pytest.raises(AuthenticationError):
        await service.refresh(tokens.refresh_token, None)


def _service(factory: async_sessionmaker[AsyncSession]) -> AuthService:
    return AuthService(
        session_factory=factory,
        settings=Settings(
            _env_file=None,
            jwt_secret="integration-secret-with-at-least-32-characters",
        ),
        clock=lambda: NOW,
    )


async def _create_identity(factory: async_sessionmaker[AsyncSession]) -> None:
    password_security = PasswordSecurity()
    organization_id = uuid.uuid4()
    user_id = uuid.uuid4()
    async with factory() as session, session.begin():
        session.add(
            Organization(
                id=organization_id,
                name="Integration Fleet",
                slug="integration-fleet",
                timezone="UTC",
                default_currency="CAD",
            )
        )
        session.add(
            User(
                id=user_id,
                email="manager@example.com",
                password_hash=password_security.hash("valid-demo-password"),
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
