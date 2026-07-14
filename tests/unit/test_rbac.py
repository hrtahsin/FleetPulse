import uuid

import pytest

from fleetpulse.auth.dependencies import require_roles
from fleetpulse.auth.roles import MembershipRole
from fleetpulse.auth.service import CurrentIdentity
from fleetpulse.shared.errors import APIError


def _identity(role: MembershipRole) -> CurrentIdentity:
    return CurrentIdentity(
        user_id=uuid.uuid4(),
        email="user@example.com",
        display_name="Test User",
        membership_id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        organization_name="Test Fleet",
        organization_slug="test-fleet",
        organization_timezone="UTC",
        default_currency="CAD",
        role=role,
    )


@pytest.mark.asyncio
async def test_role_dependency_allows_configured_role() -> None:
    dependency = require_roles(MembershipRole.OWNER, MembershipRole.MANAGER)

    assert await dependency(identity=_identity(MembershipRole.MANAGER))


@pytest.mark.asyncio
async def test_role_dependency_denies_other_role() -> None:
    dependency = require_roles(MembershipRole.OWNER, MembershipRole.MANAGER)

    with pytest.raises(APIError) as raised:
        await dependency(identity=_identity(MembershipRole.DRIVER))

    assert raised.value.status_code == 403
