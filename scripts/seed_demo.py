import asyncio
import os
import uuid

from sqlalchemy import select

from fleetpulse.auth.models import OrganizationMembership, User
from fleetpulse.auth.roles import MembershipRole
from fleetpulse.auth.security import PasswordSecurity
from fleetpulse.organizations.models import Organization
from fleetpulse.shared.database import dispose_engine, get_session_factory

DEMO_ORGANIZATION_SLUG = "demo-fleet"
DEMO_ACCOUNTS = {
    "owner@demo.fleetpulse.local": ("Demo Owner", MembershipRole.OWNER),
    "manager@demo.fleetpulse.local": ("Demo Manager", MembershipRole.MANAGER),
    "driver@demo.fleetpulse.local": ("Demo Driver", MembershipRole.DRIVER),
    "mechanic@demo.fleetpulse.local": ("Demo Mechanic", MembershipRole.MECHANIC),
}


async def seed() -> None:
    password = os.environ.get("DEMO_USER_PASSWORD", "")
    if len(password) < 12:
        raise SystemExit("DEMO_USER_PASSWORD must contain at least 12 characters")

    password_security = PasswordSecurity()
    async with get_session_factory()() as session, session.begin():
        organization = await session.scalar(
            select(Organization).where(Organization.slug == DEMO_ORGANIZATION_SLUG)
        )
        if organization is None:
            organization = Organization(
                id=uuid.uuid4(),
                name="FleetPulse Demo Fleet",
                slug=DEMO_ORGANIZATION_SLUG,
                timezone="America/St_Johns",
                default_currency="CAD",
            )
            session.add(organization)
            await session.flush()

        for email, (display_name, role) in DEMO_ACCOUNTS.items():
            user = await session.scalar(select(User).where(User.email == email))
            if user is None:
                user = User(
                    id=uuid.uuid4(),
                    email=email,
                    display_name=display_name,
                    password_hash=password_security.hash(password),
                    is_active=True,
                )
                session.add(user)
                await session.flush()
            else:
                user.display_name = display_name
                user.password_hash = password_security.hash(password)
                user.is_active = True

            membership = await session.scalar(
                select(OrganizationMembership).where(
                    OrganizationMembership.organization_id == organization.id,
                    OrganizationMembership.user_id == user.id,
                )
            )
            if membership is None:
                session.add(
                    OrganizationMembership(
                        id=uuid.uuid4(),
                        organization_id=organization.id,
                        user_id=user.id,
                        role=role,
                    )
                )
            else:
                membership.role = role

    print("Seeded demo-fleet identities:")
    for email in DEMO_ACCOUNTS:
        print(f"- {email}")


async def main() -> None:
    try:
        await seed()
    finally:
        await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
