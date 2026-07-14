import uuid
from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from fleetpulse.auth.dependencies import require_roles
from fleetpulse.auth.roles import MembershipRole
from fleetpulse.auth.service import CurrentIdentity
from fleetpulse.defects.exceptions import DefectNotFoundError
from fleetpulse.defects.schemas import DefectListResponse, DefectResponse
from fleetpulse.defects.service import DefectService
from fleetpulse.defects.types import DefectSeverity, DefectStatus
from fleetpulse.shared.errors import APIError

router = APIRouter(prefix="/defects", tags=["defects"])
defect_reader = require_roles(MembershipRole.OWNER, MembershipRole.MANAGER, MembershipRole.MECHANIC)


@lru_cache
def get_defect_service() -> DefectService:
    return DefectService()


@router.get("", response_model=DefectListResponse)
async def list_defects(
    identity: Annotated[CurrentIdentity, Depends(defect_reader)],
    service: Annotated[DefectService, Depends(get_defect_service)],
    defect_status: Annotated[DefectStatus | None, Query(alias="status")] = None,
    severity: DefectSeverity | None = None,
    vehicle_id: uuid.UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> DefectListResponse:
    records = await service.list(
        organization_id=identity.organization_id,
        status=defect_status,
        severity=severity,
        vehicle_id=vehicle_id,
        limit=limit,
    )
    return DefectListResponse(items=[DefectResponse.model_validate(record) for record in records])


@router.get("/{defect_id}", response_model=DefectResponse)
async def get_defect(
    defect_id: uuid.UUID,
    identity: Annotated[CurrentIdentity, Depends(defect_reader)],
    service: Annotated[DefectService, Depends(get_defect_service)],
) -> DefectResponse:
    try:
        record = await service.get(organization_id=identity.organization_id, defect_id=defect_id)
    except DefectNotFoundError as exc:
        raise APIError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="DEFECT_NOT_FOUND",
            message="The requested defect was not found.",
        ) from exc
    return DefectResponse.model_validate(record)
