import asyncio
import os
import uuid
from decimal import Decimal

from sqlalchemy import select

from fleetpulse.auth.models import OrganizationMembership, User
from fleetpulse.auth.roles import MembershipRole
from fleetpulse.auth.security import PasswordSecurity
from fleetpulse.organizations.models import Organization
from fleetpulse.shared.database import dispose_engine, get_session_factory
from fleetpulse.vehicles.models import Vehicle, VehicleStatusHistory
from fleetpulse.vehicles.status import VehicleStatus

DEMO_ORGANIZATION_SLUG = "demo-fleet"
DEMO_ACCOUNTS = {
    "owner@demo.fleetpulse.local": ("Demo Owner", MembershipRole.OWNER),
    "manager@demo.fleetpulse.local": ("Demo Manager", MembershipRole.MANAGER),
    "driver@demo.fleetpulse.local": ("Demo Driver", MembershipRole.DRIVER),
    "mechanic@demo.fleetpulse.local": ("Demo Mechanic", MembershipRole.MECHANIC),
}
DEMO_VEHICLES = (
    (
        "FP-101",
        "1FTFW1E50NFA00101",
        "NL-FP101",
        "Ford",
        "F-150",
        2022,
        "gasoline",
        "42180.0",
        VehicleStatus.AVAILABLE,
    ),
    (
        "FP-202",
        "1FTBW9CK5PKA00202",
        "NL-FP202",
        "Ford",
        "E-Transit",
        2023,
        "electric",
        "18740.5",
        VehicleStatus.IN_SERVICE,
    ),
    (
        "FP-303",
        "1HTMMMML7NH003303",
        "NL-FP303",
        "International",
        "MV",
        2022,
        "diesel",
        "88410.0",
        VehicleStatus.MAINTENANCE_DUE,
    ),
    (
        "FP-404",
        "2FZHAZAN6YAJ00404",
        "NL-FP404",
        "Freightliner",
        "M2",
        2020,
        "diesel",
        "126205.8",
        VehicleStatus.OUT_OF_SERVICE,
    ),
)


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

        users_by_role: dict[MembershipRole, User] = {}
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
            users_by_role[role] = user

        manager = users_by_role[MembershipRole.MANAGER]
        for (
            unit_number,
            vin,
            registration,
            make,
            model,
            model_year,
            fuel_type,
            odometer_km,
            vehicle_status,
        ) in DEMO_VEHICLES:
            vehicle = await session.scalar(
                select(Vehicle).where(
                    Vehicle.organization_id == organization.id,
                    Vehicle.unit_number == unit_number,
                )
            )
            if vehicle is not None:
                continue
            vehicle = Vehicle(
                id=uuid.uuid4(),
                organization_id=organization.id,
                unit_number=unit_number,
                vin=vin,
                registration=registration,
                make=make,
                model=model,
                model_year=model_year,
                fuel_type=fuel_type,
                odometer_km=Decimal(odometer_km),
                status=vehicle_status,
                version=1,
            )
            session.add(vehicle)
            session.add(
                VehicleStatusHistory(
                    id=uuid.uuid4(),
                    organization_id=organization.id,
                    vehicle_id=vehicle.id,
                    from_status=None,
                    to_status=vehicle_status,
                    reason_code="demo_seed",
                    changed_by_user_id=manager.id,
                )
            )

    print("Seeded demo-fleet identities:")
    for email in DEMO_ACCOUNTS:
        print(f"- {email}")
    print("Seeded demo-fleet vehicles:")
    for demo_vehicle in DEMO_VEHICLES:
        print(f"- {demo_vehicle[0]}")


async def main() -> None:
    try:
        await seed()
    finally:
        await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
