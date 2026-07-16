import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Request, Response, status

from fleetpulse.auth.dependencies import get_auth_service, get_current_identity, require_roles
from fleetpulse.auth.exceptions import (
    AuthenticationError,
    LastOwnerError,
    MemberAlreadyExistsError,
    MemberNotFoundError,
    MemberPermissionError,
)
from fleetpulse.auth.repository import MemberRecord
from fleetpulse.auth.roles import MembershipRole
from fleetpulse.auth.schemas import (
    LoginRequest,
    LogoutRequest,
    MemberCreateRequest,
    MemberListResponse,
    MemberResponse,
    MemberUpdateRequest,
    MeResponse,
    OrganizationSummary,
    RefreshRequest,
    TokenResponse,
)
from fleetpulse.auth.service import (
    AuthService,
    CreateMember,
    CurrentIdentity,
    TokenPair,
    UpdateMember,
)
from fleetpulse.shared.errors import APIError

router = APIRouter(tags=["authentication"])
member_reader = require_roles(MembershipRole.OWNER, MembershipRole.MANAGER)


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


@router.get("/members", response_model=MemberListResponse)
async def list_members(
    identity: Annotated[CurrentIdentity, Depends(member_reader)],
    service: Annotated[AuthService, Depends(get_auth_service)],
    role: Annotated[MembershipRole | None, Query()] = None,
) -> MemberListResponse:
    records = await service.list_members(identity.organization_id, role)
    return MemberListResponse(items=[_member_response(record) for record in records])


@router.post("/members", response_model=MemberResponse, status_code=status.HTTP_201_CREATED)
async def create_member(
    payload: MemberCreateRequest,
    request: Request,
    identity: Annotated[CurrentIdentity, Depends(member_reader)],
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> MemberResponse:
    try:
        record = await service.create_member(
            organization_id=identity.organization_id,
            actor_user_id=identity.user_id,
            actor_role=identity.role,
            request_id=uuid.UUID(str(request.state.request_id)),
            data=CreateMember(
                email=str(payload.email),
                display_name=payload.display_name,
                role=payload.role,
                temporary_password=payload.temporary_password,
            ),
        )
    except (MemberAlreadyExistsError, MemberPermissionError, LastOwnerError) as exc:
        raise _member_error(exc) from exc
    return _member_response(record)


@router.patch("/members/{membership_id}", response_model=MemberResponse)
async def update_member(
    membership_id: uuid.UUID,
    payload: MemberUpdateRequest,
    request: Request,
    identity: Annotated[CurrentIdentity, Depends(member_reader)],
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> MemberResponse:
    try:
        record = await service.update_member(
            organization_id=identity.organization_id,
            actor_user_id=identity.user_id,
            actor_role=identity.role,
            membership_id=membership_id,
            request_id=uuid.UUID(str(request.state.request_id)),
            data=UpdateMember(
                display_name=payload.display_name,
                role=payload.role,
                is_active=payload.is_active,
            ),
        )
    except (
        MemberNotFoundError,
        MemberPermissionError,
        LastOwnerError,
    ) as exc:
        raise _member_error(exc) from exc
    return _member_response(record)


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


def _member_response(record: MemberRecord) -> MemberResponse:
    return MemberResponse(
        membership_id=record.membership.id,
        user_id=record.user.id,
        email=record.user.email,
        display_name=record.user.display_name,
        role=MembershipRole(record.membership.role),
        is_active=record.user.is_active,
    )


def _member_error(exc: Exception) -> APIError:
    if isinstance(exc, MemberNotFoundError):
        return APIError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="MEMBER_NOT_FOUND",
            message="The requested member was not found.",
        )
    if isinstance(exc, MemberAlreadyExistsError):
        return APIError(
            status_code=status.HTTP_409_CONFLICT,
            code="MEMBER_ALREADY_EXISTS",
            message="An account with that email address already exists.",
        )
    if isinstance(exc, LastOwnerError):
        return APIError(
            status_code=status.HTTP_409_CONFLICT,
            code="LAST_OWNER_REQUIRED",
            message="The organization must retain at least one active owner.",
        )
    return APIError(
        status_code=status.HTTP_403_FORBIDDEN,
        code="MEMBER_MANAGEMENT_FORBIDDEN",
        message="You do not have permission to manage that member or role.",
    )
