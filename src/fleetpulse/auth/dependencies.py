from collections.abc import Callable, Coroutine
from functools import lru_cache
from typing import Annotated, Any

from fastapi import Depends, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from fleetpulse.auth.exceptions import AuthenticationError
from fleetpulse.auth.roles import MembershipRole
from fleetpulse.auth.service import AuthService, CurrentIdentity
from fleetpulse.shared.errors import APIError

bearer_scheme = HTTPBearer(auto_error=False)


@lru_cache
def get_auth_service() -> AuthService:
    return AuthService()


async def get_current_identity(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> CurrentIdentity:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _unauthenticated()
    try:
        return await service.current_identity(credentials.credentials)
    except AuthenticationError as exc:
        raise _unauthenticated() from exc


RoleDependency = Callable[..., Coroutine[Any, Any, CurrentIdentity]]


def require_roles(*allowed_roles: MembershipRole) -> RoleDependency:
    allowed = frozenset(allowed_roles)

    async def dependency(
        identity: Annotated[CurrentIdentity, Depends(get_current_identity)],
    ) -> CurrentIdentity:
        if identity.role not in allowed:
            raise APIError(
                status_code=status.HTTP_403_FORBIDDEN,
                code="FORBIDDEN",
                message="You do not have permission to perform this action.",
            )
        return identity

    return dependency


def _unauthenticated() -> APIError:
    return APIError(
        status_code=status.HTTP_401_UNAUTHORIZED,
        code="UNAUTHENTICATED",
        message="Authentication is required.",
    )
