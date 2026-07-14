import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from fleetpulse.auth.exceptions import AuthenticationError
from fleetpulse.auth.roles import MembershipRole
from fleetpulse.shared.config import Settings


@dataclass(frozen=True, slots=True)
class AccessClaims:
    user_id: uuid.UUID
    membership_id: uuid.UUID
    organization_id: uuid.UUID
    role: MembershipRole
    expires_at: datetime


class AccessTokenCodec:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def encode(
        self,
        *,
        user_id: uuid.UUID,
        membership_id: uuid.UUID,
        organization_id: uuid.UUID,
        role: MembershipRole,
        now: datetime | None = None,
    ) -> tuple[str, datetime]:
        issued_at = (now or datetime.now(UTC)).replace(microsecond=0)
        expires_at = issued_at + timedelta(minutes=self._settings.access_token_ttl_minutes)
        payload: dict[str, Any] = {
            "sub": str(user_id),
            "membership_id": str(membership_id),
            "organization_id": str(organization_id),
            "role": role.value,
            "type": "access",
            "jti": str(uuid.uuid4()),
            "iss": self._settings.jwt_issuer,
            "aud": self._settings.jwt_audience,
            "iat": issued_at,
            "exp": expires_at,
        }
        token = jwt.encode(
            payload,
            self._settings.jwt_secret,
            algorithm=self._settings.jwt_algorithm,
        )
        return token, expires_at

    def decode(self, token: str) -> AccessClaims:
        try:
            payload = jwt.decode(
                token,
                self._settings.jwt_secret,
                algorithms=[self._settings.jwt_algorithm],
                audience=self._settings.jwt_audience,
                issuer=self._settings.jwt_issuer,
                options={
                    "require": [
                        "sub",
                        "membership_id",
                        "organization_id",
                        "role",
                        "type",
                        "exp",
                        "iat",
                    ]
                },
            )
            if payload["type"] != "access":
                raise AuthenticationError
            return AccessClaims(
                user_id=uuid.UUID(payload["sub"]),
                membership_id=uuid.UUID(payload["membership_id"]),
                organization_id=uuid.UUID(payload["organization_id"]),
                role=MembershipRole(payload["role"]),
                expires_at=datetime.fromtimestamp(payload["exp"], tz=UTC),
            )
        except (jwt.InvalidTokenError, KeyError, TypeError, ValueError) as exc:
            raise AuthenticationError from exc
