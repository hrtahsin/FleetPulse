from dataclasses import dataclass
from datetime import datetime
from typing import cast
from uuid import UUID

from sqlalchemy import Select, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from fleetpulse.auth.models import OrganizationMembership, RefreshToken, User
from fleetpulse.organizations.models import Organization


@dataclass(frozen=True, slots=True)
class IdentityRecord:
    user: User
    membership: OrganizationMembership
    organization: Organization


class AuthRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @staticmethod
    def _identity_query() -> Select[tuple[User, OrganizationMembership, Organization]]:
        return (
            select(User, OrganizationMembership, Organization)
            .join(OrganizationMembership, OrganizationMembership.user_id == User.id)
            .join(Organization, Organization.id == OrganizationMembership.organization_id)
        )

    async def get_identity_by_email(self, email: str) -> IdentityRecord | None:
        statement = self._identity_query().where(User.email == email).limit(1)
        row = (await self._session.execute(statement)).one_or_none()
        if row is None:
            return None
        return IdentityRecord(user=row[0], membership=row[1], organization=row[2])

    async def get_identity_by_user_id(self, user_id: UUID) -> IdentityRecord | None:
        statement = self._identity_query().where(User.id == user_id).limit(1)
        row = (await self._session.execute(statement)).one_or_none()
        if row is None:
            return None
        return IdentityRecord(user=row[0], membership=row[1], organization=row[2])

    async def get_refresh_token_for_update(self, token_hash: str) -> RefreshToken | None:
        statement = (
            select(RefreshToken).where(RefreshToken.token_hash == token_hash).with_for_update()
        )
        return cast(RefreshToken | None, await self._session.scalar(statement))

    def add_refresh_token(self, token: RefreshToken) -> None:
        self._session.add(token)

    async def revoke_family(self, token: RefreshToken, revoked_at: datetime) -> None:
        await self._session.execute(
            update(RefreshToken)
            .where(
                RefreshToken.user_id == token.user_id,
                RefreshToken.family_id == token.family_id,
                RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=revoked_at)
        )
