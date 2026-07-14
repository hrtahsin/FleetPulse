import uuid
from functools import lru_cache
from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends, Header, Query, Request, Response, status

from fleetpulse.auth.dependencies import get_current_identity, require_roles
from fleetpulse.auth.roles import MembershipRole
from fleetpulse.auth.service import CurrentIdentity
from fleetpulse.inspections.exceptions import (
    IdempotencyPayloadMismatchError,
    InspectionNotFoundError,
    InspectionOdometerRollbackError,
    InspectionTemplateNotFoundError,
    InspectionVehicleNotFoundError,
    InvalidInspectionResponseError,
    MissingInspectionResponseError,
    VehicleNotInspectableError,
)
from fleetpulse.inspections.schemas import (
    ActiveInspectionTemplateResponse,
    DefectSummaryResponse,
    InspectionDetailsResponse,
    InspectionListResponse,
    InspectionResponseRecord,
    InspectionSubmitRequest,
    InspectionSummaryResponse,
    InspectionTemplateItemResponse,
)
from fleetpulse.inspections.service import (
    InspectionDetails,
    InspectionService,
    ReportedDefect,
    SubmitInspection,
    SubmittedResponse,
)
from fleetpulse.shared.errors import APIError

router = APIRouter(tags=["inspections"])
driver_identity = require_roles(MembershipRole.DRIVER)


@lru_cache
def get_inspection_service() -> InspectionService:
    return InspectionService()


@router.get("/inspection-templates/active", response_model=ActiveInspectionTemplateResponse)
async def active_template(
    identity: Annotated[CurrentIdentity, Depends(get_current_identity)],
    service: Annotated[InspectionService, Depends(get_inspection_service)],
) -> ActiveInspectionTemplateResponse:
    try:
        active = await service.active_template(identity.organization_id)
    except InspectionTemplateNotFoundError as exc:
        _raise_inspection_error(exc)
    return ActiveInspectionTemplateResponse(
        id=active.template.id,
        name=active.template.name,
        version=active.template.version,
        items=[InspectionTemplateItemResponse.model_validate(item) for item in active.items],
    )


@router.post(
    "/inspections",
    response_model=InspectionDetailsResponse,
    status_code=status.HTTP_201_CREATED,
)
async def submit_inspection(
    payload: InspectionSubmitRequest,
    request: Request,
    response: Response,
    identity: Annotated[CurrentIdentity, Depends(driver_identity)],
    service: Annotated[InspectionService, Depends(get_inspection_service)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=128)],
) -> InspectionDetailsResponse:
    try:
        details = await service.submit(
            organization_id=identity.organization_id,
            driver_membership_id=identity.membership_id,
            actor_user_id=identity.user_id,
            idempotency_key=idempotency_key,
            request_id=uuid.UUID(str(request.state.request_id)),
            submission=_submission(payload),
        )
    except (
        IdempotencyPayloadMismatchError,
        InspectionOdometerRollbackError,
        InspectionTemplateNotFoundError,
        InspectionVehicleNotFoundError,
        InvalidInspectionResponseError,
        MissingInspectionResponseError,
        VehicleNotInspectableError,
    ) as exc:
        _raise_inspection_error(exc)
    if details.replayed:
        response.status_code = status.HTTP_200_OK
    return _details_response(details)


@router.get("/inspections", response_model=InspectionListResponse)
async def list_inspections(
    identity: Annotated[CurrentIdentity, Depends(get_current_identity)],
    service: Annotated[InspectionService, Depends(get_inspection_service)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> InspectionListResponse:
    driver_membership_id = (
        identity.membership_id if identity.role is MembershipRole.DRIVER else None
    )
    records = await service.list(
        organization_id=identity.organization_id,
        driver_membership_id=driver_membership_id,
        limit=limit,
    )
    return InspectionListResponse(
        items=[InspectionSummaryResponse.model_validate(record) for record in records]
    )


@router.get("/inspections/{inspection_id}", response_model=InspectionDetailsResponse)
async def get_inspection(
    inspection_id: uuid.UUID,
    identity: Annotated[CurrentIdentity, Depends(get_current_identity)],
    service: Annotated[InspectionService, Depends(get_inspection_service)],
) -> InspectionDetailsResponse:
    try:
        details = await service.get(
            organization_id=identity.organization_id, inspection_id=inspection_id
        )
    except InspectionNotFoundError as exc:
        _raise_inspection_error(exc)
    if (
        identity.role is MembershipRole.DRIVER
        and details.inspection.driver_membership_id != identity.membership_id
    ):
        _raise_inspection_error(InspectionNotFoundError())
    return _details_response(details)


def _submission(payload: InspectionSubmitRequest) -> SubmitInspection:
    return SubmitInspection(
        vehicle_id=payload.vehicle_id,
        template_id=payload.template_id,
        odometer_km=payload.odometer_km,
        notes=payload.notes,
        responses=[
            SubmittedResponse(
                template_item_id=item.template_item_id,
                result=item.result,
                comment=item.comment,
                defect=(
                    ReportedDefect(
                        category=item.defect.category,
                        description=item.defect.description,
                        severity=item.defect.severity,
                    )
                    if item.defect
                    else None
                ),
            )
            for item in payload.responses
        ],
    )


def _details_response(details: InspectionDetails) -> InspectionDetailsResponse:
    defects_by_response_id = {
        defect.inspection_response_id: defect
        for defect in details.defects
        if defect.inspection_response_id is not None
    }
    responses = []
    for record in details.responses:
        defect = defects_by_response_id.get(record.id)
        responses.append(
            InspectionResponseRecord(
                id=record.id,
                template_item_id=record.template_item_id,
                result=record.result,
                comment=record.comment,
                defect=(DefectSummaryResponse.model_validate(defect) if defect else None),
            )
        )
    inspection = details.inspection
    return InspectionDetailsResponse(
        id=inspection.id,
        vehicle_id=inspection.vehicle_id,
        driver_membership_id=inspection.driver_membership_id,
        template_id=inspection.template_id,
        odometer_km=inspection.odometer_km,
        status=inspection.status,
        notes=inspection.notes,
        submitted_at=inspection.submitted_at,
        responses=responses,
        defects=[DefectSummaryResponse.model_validate(defect) for defect in details.defects],
        replayed=details.replayed,
    )


def _raise_inspection_error(exc: Exception) -> NoReturn:
    if isinstance(exc, (InspectionNotFoundError, InspectionVehicleNotFoundError)):
        raise APIError(
            status_code=status.HTTP_404_NOT_FOUND,
            code=(
                "INSPECTION_NOT_FOUND"
                if isinstance(exc, InspectionNotFoundError)
                else "VEHICLE_NOT_FOUND"
            ),
            message="The requested inspection resource was not found.",
        ) from exc
    if isinstance(exc, InspectionTemplateNotFoundError):
        raise APIError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="INSPECTION_TEMPLATE_NOT_FOUND",
            message="An active inspection template was not found.",
        ) from exc
    if isinstance(exc, IdempotencyPayloadMismatchError):
        raise APIError(
            status_code=status.HTTP_409_CONFLICT,
            code="IDEMPOTENCY_PAYLOAD_MISMATCH",
            message="The idempotency key was already used with a different payload.",
        ) from exc
    if isinstance(exc, VehicleNotInspectableError):
        raise APIError(
            status_code=status.HTTP_409_CONFLICT,
            code="VEHICLE_NOT_INSPECTABLE",
            message="The vehicle is not in an inspectable operational state.",
        ) from exc
    if isinstance(exc, InspectionOdometerRollbackError):
        raise APIError(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            code="ODOMETER_ROLLBACK",
            message="The inspection odometer cannot be lower than the current reading.",
        ) from exc
    if isinstance(exc, MissingInspectionResponseError):
        raise APIError(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            code="MISSING_REQUIRED_RESPONSE",
            message="Every required inspection item must be answered.",
        ) from exc
    if isinstance(exc, InvalidInspectionResponseError):
        raise APIError(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            code="INVALID_INSPECTION_RESPONSE",
            message="One or more inspection responses are invalid.",
        ) from exc
    raise exc
