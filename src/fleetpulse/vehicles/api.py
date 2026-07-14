from functools import lru_cache
from typing import Annotated, NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from fleetpulse.auth.dependencies import get_current_identity, require_roles
from fleetpulse.auth.roles import MembershipRole
from fleetpulse.auth.service import CurrentIdentity
from fleetpulse.shared.errors import APIError
from fleetpulse.vehicles.exceptions import (
    DuplicateVehicleError,
    InvalidStatusTransitionError,
    InvalidVehicleCursorError,
    OdometerRollbackError,
    StaleVehicleVersionError,
    StatusReasonRequiredError,
    VehicleNotFoundError,
)
from fleetpulse.vehicles.schemas import (
    VehicleCreateRequest,
    VehicleHistoryListResponse,
    VehicleListResponse,
    VehicleResponse,
    VehicleUpdateRequest,
)
from fleetpulse.vehicles.service import CreateVehicle, VehicleService
from fleetpulse.vehicles.status import VehicleStatus

router = APIRouter(prefix="/vehicles", tags=["vehicles"])
management_identity = require_roles(MembershipRole.OWNER, MembershipRole.MANAGER)


@lru_cache
def get_vehicle_service() -> VehicleService:
    return VehicleService()


@router.get("", response_model=VehicleListResponse)
async def list_vehicles(
    identity: Annotated[CurrentIdentity, Depends(get_current_identity)],
    service: Annotated[VehicleService, Depends(get_vehicle_service)],
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    cursor: Annotated[str | None, Query(max_length=100)] = None,
    vehicle_status: Annotated[VehicleStatus | None, Query(alias="status")] = None,
    query: Annotated[str | None, Query(alias="q", min_length=1, max_length=100)] = None,
) -> VehicleListResponse:
    try:
        page = await service.list(
            organization_id=identity.organization_id,
            limit=limit,
            cursor=cursor,
            status=vehicle_status,
            query=query,
        )
    except InvalidVehicleCursorError as exc:
        raise APIError(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            code="INVALID_CURSOR",
            message="The supplied pagination cursor is invalid.",
        ) from exc
    return VehicleListResponse(
        items=[VehicleResponse.model_validate(vehicle) for vehicle in page.items],
        next_cursor=page.next_cursor,
    )


@router.post("", response_model=VehicleResponse, status_code=status.HTTP_201_CREATED)
async def create_vehicle(
    payload: VehicleCreateRequest,
    identity: Annotated[CurrentIdentity, Depends(management_identity)],
    service: Annotated[VehicleService, Depends(get_vehicle_service)],
) -> VehicleResponse:
    try:
        vehicle = await service.create(
            organization_id=identity.organization_id,
            actor_user_id=identity.user_id,
            data=CreateVehicle(**payload.model_dump()),
        )
    except DuplicateVehicleError as exc:
        _raise_vehicle_error(exc)
    return VehicleResponse.model_validate(vehicle)


@router.get("/{vehicle_id}", response_model=VehicleResponse)
async def get_vehicle(
    vehicle_id: UUID,
    identity: Annotated[CurrentIdentity, Depends(get_current_identity)],
    service: Annotated[VehicleService, Depends(get_vehicle_service)],
) -> VehicleResponse:
    try:
        vehicle = await service.get(organization_id=identity.organization_id, vehicle_id=vehicle_id)
    except VehicleNotFoundError as exc:
        _raise_vehicle_error(exc)
    return VehicleResponse.model_validate(vehicle)


@router.patch("/{vehicle_id}", response_model=VehicleResponse)
async def update_vehicle(
    vehicle_id: UUID,
    payload: VehicleUpdateRequest,
    identity: Annotated[CurrentIdentity, Depends(management_identity)],
    service: Annotated[VehicleService, Depends(get_vehicle_service)],
) -> VehicleResponse:
    try:
        vehicle = await service.update(
            organization_id=identity.organization_id,
            vehicle_id=vehicle_id,
            actor_user_id=identity.user_id,
            expected_version=payload.version,
            changes=payload.changes(),
            status_reason=payload.status_reason,
        )
    except (
        VehicleNotFoundError,
        DuplicateVehicleError,
        InvalidStatusTransitionError,
        OdometerRollbackError,
        StatusReasonRequiredError,
        StaleVehicleVersionError,
    ) as exc:
        _raise_vehicle_error(exc)
    return VehicleResponse.model_validate(vehicle)


@router.get("/{vehicle_id}/history", response_model=VehicleHistoryListResponse)
async def get_vehicle_history(
    vehicle_id: UUID,
    identity: Annotated[CurrentIdentity, Depends(get_current_identity)],
    service: Annotated[VehicleService, Depends(get_vehicle_service)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> VehicleHistoryListResponse:
    try:
        records = await service.history(
            organization_id=identity.organization_id,
            vehicle_id=vehicle_id,
            limit=limit,
        )
    except VehicleNotFoundError as exc:
        _raise_vehicle_error(exc)
    return VehicleHistoryListResponse(items=list(records))


def _raise_vehicle_error(exc: Exception) -> NoReturn:
    if isinstance(exc, VehicleNotFoundError):
        raise APIError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="VEHICLE_NOT_FOUND",
            message="The requested vehicle was not found.",
        ) from exc
    if isinstance(exc, DuplicateVehicleError):
        raise APIError(
            status_code=status.HTTP_409_CONFLICT,
            code="VEHICLE_ALREADY_EXISTS",
            message="A vehicle with that unit number or VIN already exists.",
        ) from exc
    if isinstance(exc, StaleVehicleVersionError):
        raise APIError(
            status_code=status.HTTP_409_CONFLICT,
            code="STALE_VEHICLE_VERSION",
            message="The vehicle changed since it was last loaded.",
        ) from exc
    if isinstance(exc, InvalidStatusTransitionError):
        raise APIError(
            status_code=status.HTTP_409_CONFLICT,
            code="INVALID_STATUS_TRANSITION",
            message="The requested vehicle status transition is not allowed.",
        ) from exc
    if isinstance(exc, OdometerRollbackError):
        raise APIError(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            code="ODOMETER_ROLLBACK",
            message="The odometer reading cannot be lower than the current reading.",
        ) from exc
    if isinstance(exc, StatusReasonRequiredError):
        raise APIError(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            code="STATUS_REASON_REQUIRED",
            message="A reason is required when changing vehicle status.",
        ) from exc
    raise exc
