import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fleetpulse.audit.models import AuditEvent
from fleetpulse.auth.exceptions import (
    AuthenticationError,
    LastOwnerError,
    MemberNotFoundError,
    MemberPermissionError,
    TokenReuseError,
)
from fleetpulse.auth.models import OrganizationMembership, RefreshToken, User
from fleetpulse.auth.roles import MembershipRole
from fleetpulse.auth.security import PasswordSecurity
from fleetpulse.auth.service import AuthService, CreateMember, UpdateMember
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


@pytest.mark.asyncio
async def test_manager_creates_and_deactivates_operational_member(
    auth_database: async_sessionmaker[AsyncSession],
) -> None:
    organization_id, manager_id, _ = await _create_identity(auth_database)
    service = _service(auth_database)
    created = await service.create_member(
        organization_id=organization_id,
        actor_user_id=manager_id,
        actor_role=MembershipRole.MANAGER,
        request_id=uuid.uuid4(),
        data=CreateMember(
            email="driver@example.com",
            display_name="Integration Driver",
            role=MembershipRole.DRIVER,
            temporary_password="temporary-driver-password",
        ),
    )
    tokens = await service.login("driver@example.com", "temporary-driver-password", None)

    updated = await service.update_member(
        organization_id=organization_id,
        actor_user_id=manager_id,
        actor_role=MembershipRole.MANAGER,
        membership_id=created.membership.id,
        request_id=uuid.uuid4(),
        data=UpdateMember(is_active=False),
    )

    assert updated.user.is_active is False
    with pytest.raises(AuthenticationError):
        await service.current_identity(tokens.access_token)
    with pytest.raises(AuthenticationError):
        await service.refresh(tokens.refresh_token, None)
    async with auth_database() as session:
        audit_actions = list(await session.scalars(select(AuditEvent.action)))
    assert audit_actions == ["membership.created", "membership.updated"]


@pytest.mark.asyncio
async def test_member_management_enforces_roles_tenant_and_last_owner(
    auth_database: async_sessionmaker[AsyncSession],
) -> None:
    organization_id, owner_id, owner_membership_id = await _create_identity(
        auth_database, role=MembershipRole.OWNER
    )
    other_organization_id, _, _ = await _create_identity(
        auth_database,
        role=MembershipRole.MANAGER,
        slug="other-fleet",
        email="other-manager@example.com",
    )
    service = _service(auth_database)

    with pytest.raises(MemberPermissionError):
        await service.create_member(
            organization_id=organization_id,
            actor_user_id=uuid.uuid4(),
            actor_role=MembershipRole.MANAGER,
            request_id=uuid.uuid4(),
            data=CreateMember(
                email="second-manager@example.com",
                display_name="Second Manager",
                role=MembershipRole.MANAGER,
                temporary_password="temporary-manager-password",
            ),
        )
    with pytest.raises(MemberNotFoundError):
        await service.update_member(
            organization_id=other_organization_id,
            actor_user_id=owner_id,
            actor_role=MembershipRole.OWNER,
            membership_id=owner_membership_id,
            request_id=uuid.uuid4(),
            data=UpdateMember(display_name="Cross tenant"),
        )
    with pytest.raises(LastOwnerError):
        await service.update_member(
            organization_id=organization_id,
            actor_user_id=uuid.uuid4(),
            actor_role=MembershipRole.OWNER,
            membership_id=owner_membership_id,
            request_id=uuid.uuid4(),
            data=UpdateMember(role=MembershipRole.MANAGER),
        )


def _service(factory: async_sessionmaker[AsyncSession]) -> AuthService:
    return AuthService(
        session_factory=factory,
        settings=Settings(
            _env_file=None,
            jwt_secret="integration-secret-with-at-least-32-characters",
        ),
        clock=lambda: NOW,
    )


async def _create_identity(
    factory: async_sessionmaker[AsyncSession],
    *,
    role: MembershipRole = MembershipRole.MANAGER,
    slug: str = "integration-fleet",
    email: str = "manager@example.com",
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    password_security = PasswordSecurity()
    organization_id = uuid.uuid4()
    user_id = uuid.uuid4()
    membership_id = uuid.uuid4()
    async with factory() as session, session.begin():
        session.add(
            Organization(
                id=organization_id,
                name="Integration Fleet",
                slug=slug,
                timezone="UTC",
                default_currency="CAD",
            )
        )
        session.add(
            User(
                id=user_id,
                email=email,
                password_hash=password_security.hash("valid-demo-password"),
                display_name="Integration Manager",
                is_active=True,
            )
        )
        await session.flush()
        session.add(
            OrganizationMembership(
                id=membership_id,
                organization_id=organization_id,
                user_id=user_id,
                role=role,
            )
        )
    return organization_id, user_id, membership_id
