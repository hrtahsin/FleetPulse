import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fleetpulse.auth.exceptions import AuthenticationError, TokenReuseError
from fleetpulse.auth.models import RefreshToken
from fleetpulse.auth.repository import AuthRepository, IdentityRecord, MemberRecord
from fleetpulse.auth.roles import MembershipRole
from fleetpulse.auth.security import (
    PasswordSecurity,
    generate_refresh_token,
    hash_refresh_token,
    hash_user_agent,
)
from fleetpulse.auth.tokens import AccessTokenCodec
from fleetpulse.shared.config import Settings, get_settings
from fleetpulse.shared.database import get_session_factory


@dataclass(frozen=True, slots=True)
class TokenPair:
    access_token: str
    refresh_token: str
    access_expires_at: datetime


@dataclass(frozen=True, slots=True)
class CurrentIdentity:
    user_id: uuid.UUID
    email: str
    display_name: str
    membership_id: uuid.UUID
    organization_id: uuid.UUID
    organization_name: str
    organization_slug: str
    organization_timezone: str
    default_currency: str
    role: MembershipRole


class AuthService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
        settings: Settings | None = None,
        password_security: PasswordSecurity | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._session_factory = session_factory or get_session_factory()
        self._settings = settings or get_settings()
        self._passwords = password_security or PasswordSecurity()
        self._tokens = AccessTokenCodec(self._settings)
        self._clock = clock or (lambda: datetime.now(UTC))

    async def login(self, email: str, password: str, user_agent: str | None) -> TokenPair:
        normalized_email = email.strip().lower()
        now = self._clock()
        async with self._session_factory() as session, session.begin():
            repository = AuthRepository(session)
            identity = await repository.get_identity_by_email(normalized_email)
            password_hash = identity.user.password_hash if identity else None
            if not self._passwords.verify_or_dummy(password, password_hash):
                raise AuthenticationError
            if identity is None or not identity.user.is_active:
                raise AuthenticationError

            if self._passwords.needs_rehash(identity.user.password_hash):
                identity.user.password_hash = self._passwords.hash(password)
            identity.user.last_login_at = now
            raw_refresh_token = generate_refresh_token()
            repository.add_refresh_token(
                self._new_refresh_token(
                    identity=identity,
                    raw_token=raw_refresh_token,
                    family_id=uuid.uuid4(),
                    user_agent=user_agent,
                    now=now,
                )
            )
            return self._token_pair(identity, raw_refresh_token, now)

    async def refresh(self, raw_refresh_token: str, user_agent: str | None) -> TokenPair:
        now = self._clock()
        result: TokenPair | None = None
        failure: AuthenticationError | None = None

        async with self._session_factory() as session, session.begin():
            repository = AuthRepository(session)
            stored = await repository.get_refresh_token_for_update(
                hash_refresh_token(raw_refresh_token)
            )
            if stored is None:
                raise AuthenticationError

            if stored.revoked_at is not None:
                if stored.replaced_by_token_id is not None:
                    await repository.revoke_family(stored, now)
                    failure = TokenReuseError()
                else:
                    failure = AuthenticationError()
            elif stored.expires_at <= now:
                stored.revoked_at = now
                failure = AuthenticationError()
            else:
                identity = await repository.get_identity_by_user_id(stored.user_id)
                if identity is None or not identity.user.is_active:
                    await repository.revoke_family(stored, now)
                    failure = AuthenticationError()
                else:
                    replacement_raw = generate_refresh_token()
                    replacement = self._new_refresh_token(
                        identity=identity,
                        raw_token=replacement_raw,
                        family_id=stored.family_id,
                        user_agent=user_agent,
                        now=now,
                    )
                    repository.add_refresh_token(replacement)
                    await session.flush()
                    stored.revoked_at = now
                    stored.replaced_by_token_id = replacement.id
                    result = self._token_pair(identity, replacement_raw, now)

        if failure is not None:
            raise failure
        if result is None:
            raise AuthenticationError
        return result

    async def logout(self, raw_refresh_token: str) -> None:
        now = self._clock()
        async with self._session_factory() as session, session.begin():
            repository = AuthRepository(session)
            stored = await repository.get_refresh_token_for_update(
                hash_refresh_token(raw_refresh_token)
            )
            if stored is not None and stored.revoked_at is None:
                stored.revoked_at = now

    async def current_identity(self, raw_access_token: str) -> CurrentIdentity:
        claims = self._tokens.decode(raw_access_token)
        async with self._session_factory() as session:
            repository = AuthRepository(session)
            identity = await repository.get_identity_by_user_id(claims.user_id)
        if identity is None or not identity.user.is_active:
            raise AuthenticationError
        role = MembershipRole(identity.membership.role)
        if (
            identity.membership.id != claims.membership_id
            or identity.organization.id != claims.organization_id
            or role is not claims.role
        ):
            raise AuthenticationError
        return CurrentIdentity(
            user_id=identity.user.id,
            email=identity.user.email,
            display_name=identity.user.display_name,
            membership_id=identity.membership.id,
            organization_id=identity.organization.id,
            organization_name=identity.organization.name,
            organization_slug=identity.organization.slug,
            organization_timezone=identity.organization.timezone,
            default_currency=identity.organization.default_currency,
            role=role,
        )

    async def list_members(
        self, organization_id: uuid.UUID, role: MembershipRole | None
    ) -> list[MemberRecord]:
        async with self._session_factory() as session:
            return await AuthRepository(session).list_members(organization_id, role)

    def _new_refresh_token(
        self,
        *,
        identity: IdentityRecord,
        raw_token: str,
        family_id: uuid.UUID,
        user_agent: str | None,
        now: datetime,
    ) -> RefreshToken:
        return RefreshToken(
            id=uuid.uuid4(),
            user_id=identity.user.id,
            family_id=family_id,
            token_hash=hash_refresh_token(raw_token),
            expires_at=now + timedelta(days=self._settings.refresh_token_ttl_days),
            created_at=now,
            user_agent_hash=hash_user_agent(user_agent),
        )

    def _token_pair(
        self, identity: IdentityRecord, raw_refresh_token: str, now: datetime
    ) -> TokenPair:
        access_token, expires_at = self._tokens.encode(
            user_id=identity.user.id,
            membership_id=identity.membership.id,
            organization_id=identity.organization.id,
            role=MembershipRole(identity.membership.role),
            now=now,
        )
        return TokenPair(
            access_token=access_token,
            refresh_token=raw_refresh_token,
            access_expires_at=expires_at,
        )
