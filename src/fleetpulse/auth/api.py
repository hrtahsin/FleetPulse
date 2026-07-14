from typing import Annotated

from fastapi import APIRouter, Depends, Header, Response, status

from fleetpulse.auth.dependencies import get_auth_service, get_current_identity
from fleetpulse.auth.exceptions import AuthenticationError
from fleetpulse.auth.schemas import (
    LoginRequest,
    LogoutRequest,
    MeResponse,
    OrganizationSummary,
    RefreshRequest,
    TokenResponse,
)
from fleetpulse.auth.service import AuthService, CurrentIdentity, TokenPair
from fleetpulse.shared.errors import APIError

router = APIRouter(tags=["authentication"])


@router.post("/auth/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    service: Annotated[AuthService, Depends(get_auth_service)],
    user_agent: Annotated[str | None, Header(max_length=512)] = None,
) -> TokenResponse:
    try:
        tokens = await service.login(str(payload.email), payload.password, user_agent)
    except AuthenticationError as exc:
        raise _authentication_failed() from exc
    return _token_response(tokens)


@router.post("/auth/refresh", response_model=TokenResponse)
async def refresh(
    payload: RefreshRequest,
    service: Annotated[AuthService, Depends(get_auth_service)],
    user_agent: Annotated[str | None, Header(max_length=512)] = None,
) -> TokenResponse:
    try:
        tokens = await service.refresh(payload.refresh_token, user_agent)
    except AuthenticationError as exc:
        raise _authentication_failed() from exc
    return _token_response(tokens)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    payload: LogoutRequest,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> Response:
    await service.logout(payload.refresh_token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=MeResponse)
async def me(
    identity: Annotated[CurrentIdentity, Depends(get_current_identity)],
) -> MeResponse:
    return MeResponse(
        id=identity.user_id,
        email=identity.email,
        display_name=identity.display_name,
        membership_id=identity.membership_id,
        role=identity.role,
        organization=OrganizationSummary(
            id=identity.organization_id,
            name=identity.organization_name,
            slug=identity.organization_slug,
            timezone=identity.organization_timezone,
            default_currency=identity.default_currency,
        ),
    )


def _token_response(tokens: TokenPair) -> TokenResponse:
    return TokenResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_at=tokens.access_expires_at,
    )


def _authentication_failed() -> APIError:
    return APIError(
        status_code=status.HTTP_401_UNAUTHORIZED,
        code="AUTHENTICATION_FAILED",
        message="The supplied credentials or token could not be authenticated.",
    )
