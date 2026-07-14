import uuid
from functools import lru_cache
from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends, Query, Request, status

from fleetpulse.auth.dependencies import require_roles
from fleetpulse.auth.roles import MembershipRole
from fleetpulse.auth.service import CurrentIdentity
from fleetpulse.maintenance.exceptions import (
    InvalidMaintenanceRuleError,
    MaintenanceRuleNotFoundError,
    MaintenanceVehicleNotFoundError,
)
from fleetpulse.maintenance.schemas import (
    MaintenanceEvaluationResponse,
    MaintenanceRuleCreateRequest,
    MaintenanceRuleListResponse,
    MaintenanceRuleResponse,
    MaintenanceRuleUpdateRequest,
    MaintenanceScheduleListResponse,
    MaintenanceScheduleResponse,
)
from fleetpulse.maintenance.service import CreateMaintenanceRule, MaintenanceService
from fleetpulse.maintenance.types import MaintenanceScheduleStatus
from fleetpulse.shared.errors import APIError

router = APIRouter(tags=["maintenance"])
management_identity = require_roles(MembershipRole.OWNER, MembershipRole.MANAGER)
maintenance_reader_identity = require_roles(
    MembershipRole.OWNER,
    MembershipRole.MANAGER,
    MembershipRole.MECHANIC,
)


@lru_cache
def get_maintenance_service() -> MaintenanceService:
    return MaintenanceService()


@router.get("/maintenance-rules", response_model=MaintenanceRuleListResponse)
async def list_rules(
    identity: Annotated[CurrentIdentity, Depends(management_identity)],
    service: Annotated[MaintenanceService, Depends(get_maintenance_service)],
) -> MaintenanceRuleListResponse:
    rules = await service.list_rules(identity.organization_id)
    return MaintenanceRuleListResponse(
        items=[MaintenanceRuleResponse.model_validate(rule) for rule in rules]
    )


@router.post(
    "/maintenance-rules",
    response_model=MaintenanceRuleResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_rule(
    payload: MaintenanceRuleCreateRequest,
    request: Request,
    identity: Annotated[CurrentIdentity, Depends(management_identity)],
    service: Annotated[MaintenanceService, Depends(get_maintenance_service)],
) -> MaintenanceRuleResponse:
    try:
        rule = await service.create_rule(
            organization_id=identity.organization_id,
            actor_user_id=identity.user_id,
            request_id=uuid.UUID(str(request.state.request_id)),
            data=CreateMaintenanceRule(**payload.model_dump()),
        )
    except (InvalidMaintenanceRuleError, MaintenanceVehicleNotFoundError) as exc:
        _raise_maintenance_error(exc)
    return MaintenanceRuleResponse.model_validate(rule)


@router.patch("/maintenance-rules/{rule_id}", response_model=MaintenanceRuleResponse)
async def update_rule(
    rule_id: uuid.UUID,
    payload: MaintenanceRuleUpdateRequest,
    request: Request,
    identity: Annotated[CurrentIdentity, Depends(management_identity)],
    service: Annotated[MaintenanceService, Depends(get_maintenance_service)],
) -> MaintenanceRuleResponse:
    try:
        rule = await service.update_rule(
            organization_id=identity.organization_id,
            rule_id=rule_id,
            actor_user_id=identity.user_id,
            request_id=uuid.UUID(str(request.state.request_id)),
            changes=payload.changes(),
        )
    except (
        InvalidMaintenanceRuleError,
        MaintenanceRuleNotFoundError,
        MaintenanceVehicleNotFoundError,
    ) as exc:
        _raise_maintenance_error(exc)
    return MaintenanceRuleResponse.model_validate(rule)


@router.get("/maintenance-schedules", response_model=MaintenanceScheduleListResponse)
async def list_schedules(
    identity: Annotated[CurrentIdentity, Depends(maintenance_reader_identity)],
    service: Annotated[MaintenanceService, Depends(get_maintenance_service)],
    schedule_status: Annotated[MaintenanceScheduleStatus | None, Query(alias="status")] = None,
) -> MaintenanceScheduleListResponse:
    schedules = await service.list_schedules(
        identity.organization_id,
        status=schedule_status,
    )
    return MaintenanceScheduleListResponse(
        items=[MaintenanceScheduleResponse.model_validate(item) for item in schedules]
    )


@router.post(
    "/maintenance-schedules/evaluate",
    response_model=MaintenanceEvaluationResponse,
)
async def evaluate_schedules(
    request: Request,
    identity: Annotated[CurrentIdentity, Depends(management_identity)],
    service: Annotated[MaintenanceService, Depends(get_maintenance_service)],
) -> MaintenanceEvaluationResponse:
    result = await service.evaluate(
        organization_id=identity.organization_id,
        actor_user_id=identity.user_id,
        request_id=uuid.UUID(str(request.state.request_id)),
    )
    return MaintenanceEvaluationResponse(
        created=result.created,
        updated=result.updated,
        due=result.due,
        overdue=result.overdue,
        schedules=[MaintenanceScheduleResponse.model_validate(item) for item in result.schedules],
    )


def _raise_maintenance_error(exc: Exception) -> NoReturn:
    if isinstance(exc, MaintenanceRuleNotFoundError):
        raise APIError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="MAINTENANCE_RULE_NOT_FOUND",
            message="The requested maintenance rule was not found.",
        ) from exc
    if isinstance(exc, MaintenanceVehicleNotFoundError):
        raise APIError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="VEHICLE_NOT_FOUND",
            message="The requested vehicle was not found.",
        ) from exc
    if isinstance(exc, InvalidMaintenanceRuleError):
        raise APIError(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            code="INVALID_MAINTENANCE_RULE",
            message="A positive date or odometer interval is required.",
        ) from exc
    raise exc
