import uuid
from decimal import Decimal
from functools import lru_cache
from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends, Query, Request, status

from fleetpulse.auth.dependencies import require_roles
from fleetpulse.auth.roles import MembershipRole
from fleetpulse.auth.service import CurrentIdentity
from fleetpulse.shared.errors import APIError
from fleetpulse.work_orders.exceptions import (
    WorkOrderClosedError,
    WorkOrderInvalidTransitionError,
    WorkOrderMechanicNotFoundError,
    WorkOrderNotFoundError,
    WorkOrderPermissionError,
    WorkOrderSourceConflictError,
    WorkOrderSourceNotFoundError,
    WorkOrderStaleVersionError,
    WorkOrderVerificationNoteRequiredError,
)
from fleetpulse.work_orders.schemas import (
    DefectWorkOrderCreateRequest,
    WorkOrderCostItemCreateRequest,
    WorkOrderCostItemResponse,
    WorkOrderCostItemResultResponse,
    WorkOrderCreateRequest,
    WorkOrderDetailsResponse,
    WorkOrderListResponse,
    WorkOrderNoteCreateRequest,
    WorkOrderNoteResponse,
    WorkOrderResponse,
    WorkOrderTransitionRequest,
    WorkOrderUpdateRequest,
)
from fleetpulse.work_orders.service import (
    AddCostItem,
    CreateWorkOrder,
    WorkOrderDetails,
    WorkOrderService,
)
from fleetpulse.work_orders.types import WorkOrderStatus

router = APIRouter(tags=["work orders"])
management_identity = require_roles(MembershipRole.OWNER, MembershipRole.MANAGER)
work_order_identity = require_roles(
    MembershipRole.OWNER, MembershipRole.MANAGER, MembershipRole.MECHANIC
)


@lru_cache
def get_work_order_service() -> WorkOrderService:
    return WorkOrderService()


@router.get("/work-orders", response_model=WorkOrderListResponse)
async def list_work_orders(
    identity: Annotated[CurrentIdentity, Depends(work_order_identity)],
    service: Annotated[WorkOrderService, Depends(get_work_order_service)],
    work_order_status: Annotated[WorkOrderStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> WorkOrderListResponse:
    records = await service.list(
        organization_id=identity.organization_id,
        actor_role=identity.role,
        actor_membership_id=identity.membership_id,
        status=work_order_status,
        limit=limit,
    )
    return WorkOrderListResponse(
        items=[WorkOrderResponse.model_validate(record) for record in records]
    )


@router.post(
    "/work-orders",
    response_model=WorkOrderResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_work_order(
    payload: WorkOrderCreateRequest,
    request: Request,
    identity: Annotated[CurrentIdentity, Depends(management_identity)],
    service: Annotated[WorkOrderService, Depends(get_work_order_service)],
) -> WorkOrderResponse:
    try:
        order = await service.create(
            organization_id=identity.organization_id,
            actor_user_id=identity.user_id,
            request_id=uuid.UUID(str(request.state.request_id)),
            data=CreateWorkOrder(**payload.model_dump(), currency=identity.default_currency),
        )
    except Exception as exc:
        _raise_work_order_error(exc)
    return WorkOrderResponse.model_validate(order)


@router.post(
    "/defects/{defect_id}/work-order",
    response_model=WorkOrderResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_defect_work_order(
    defect_id: uuid.UUID,
    payload: DefectWorkOrderCreateRequest,
    request: Request,
    identity: Annotated[CurrentIdentity, Depends(management_identity)],
    service: Annotated[WorkOrderService, Depends(get_work_order_service)],
) -> WorkOrderResponse:
    try:
        order = await service.create(
            organization_id=identity.organization_id,
            actor_user_id=identity.user_id,
            request_id=uuid.UUID(str(request.state.request_id)),
            data=CreateWorkOrder(
                source_defect_id=defect_id,
                maintenance_schedule_id=None,
                currency=identity.default_currency,
                **payload.model_dump(),
            ),
        )
    except Exception as exc:
        _raise_work_order_error(exc)
    return WorkOrderResponse.model_validate(order)


@router.get("/work-orders/{work_order_id}", response_model=WorkOrderDetailsResponse)
async def get_work_order(
    work_order_id: uuid.UUID,
    identity: Annotated[CurrentIdentity, Depends(work_order_identity)],
    service: Annotated[WorkOrderService, Depends(get_work_order_service)],
) -> WorkOrderDetailsResponse:
    try:
        details = await service.get(
            organization_id=identity.organization_id,
            work_order_id=work_order_id,
            actor_role=identity.role,
            actor_membership_id=identity.membership_id,
        )
    except Exception as exc:
        _raise_work_order_error(exc)
    return _details_response(details)


@router.patch("/work-orders/{work_order_id}", response_model=WorkOrderResponse)
async def update_work_order(
    work_order_id: uuid.UUID,
    payload: WorkOrderUpdateRequest,
    request: Request,
    identity: Annotated[CurrentIdentity, Depends(management_identity)],
    service: Annotated[WorkOrderService, Depends(get_work_order_service)],
) -> WorkOrderResponse:
    try:
        order = await service.update(
            organization_id=identity.organization_id,
            work_order_id=work_order_id,
            actor_user_id=identity.user_id,
            request_id=uuid.UUID(str(request.state.request_id)),
            expected_version=payload.version,
            changes=payload.changes(),
        )
    except Exception as exc:
        _raise_work_order_error(exc)
    return WorkOrderResponse.model_validate(order)


@router.post("/work-orders/{work_order_id}/transitions", response_model=WorkOrderResponse)
async def transition_work_order(
    work_order_id: uuid.UUID,
    payload: WorkOrderTransitionRequest,
    request: Request,
    identity: Annotated[CurrentIdentity, Depends(work_order_identity)],
    service: Annotated[WorkOrderService, Depends(get_work_order_service)],
) -> WorkOrderResponse:
    try:
        order = await service.transition(
            organization_id=identity.organization_id,
            work_order_id=work_order_id,
            actor_user_id=identity.user_id,
            actor_membership_id=identity.membership_id,
            actor_role=identity.role,
            request_id=uuid.UUID(str(request.state.request_id)),
            expected_version=payload.version,
            next_status=payload.status,
            note=payload.note,
        )
    except Exception as exc:
        _raise_work_order_error(exc)
    return WorkOrderResponse.model_validate(order)


@router.post(
    "/work-orders/{work_order_id}/notes",
    response_model=WorkOrderNoteResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_work_order_note(
    work_order_id: uuid.UUID,
    payload: WorkOrderNoteCreateRequest,
    request: Request,
    identity: Annotated[CurrentIdentity, Depends(work_order_identity)],
    service: Annotated[WorkOrderService, Depends(get_work_order_service)],
) -> WorkOrderNoteResponse:
    try:
        note = await service.add_note(
            organization_id=identity.organization_id,
            work_order_id=work_order_id,
            actor_user_id=identity.user_id,
            actor_membership_id=identity.membership_id,
            actor_role=identity.role,
            request_id=uuid.UUID(str(request.state.request_id)),
            body=payload.body,
        )
    except Exception as exc:
        _raise_work_order_error(exc)
    return WorkOrderNoteResponse.model_validate(note)


@router.post(
    "/work-orders/{work_order_id}/cost-items",
    response_model=WorkOrderCostItemResultResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_work_order_cost_item(
    work_order_id: uuid.UUID,
    payload: WorkOrderCostItemCreateRequest,
    request: Request,
    identity: Annotated[CurrentIdentity, Depends(work_order_identity)],
    service: Annotated[WorkOrderService, Depends(get_work_order_service)],
) -> WorkOrderCostItemResultResponse:
    try:
        item, order = await service.add_cost_item(
            organization_id=identity.organization_id,
            work_order_id=work_order_id,
            actor_user_id=identity.user_id,
            actor_membership_id=identity.membership_id,
            actor_role=identity.role,
            request_id=uuid.UUID(str(request.state.request_id)),
            expected_version=payload.version,
            data=AddCostItem(
                kind=payload.kind,
                description=payload.description,
                quantity=payload.quantity,
                unit_cost=payload.unit_cost,
            ),
        )
    except Exception as exc:
        _raise_work_order_error(exc)
    return WorkOrderCostItemResultResponse(
        item=WorkOrderCostItemResponse.model_validate(item),
        work_order=WorkOrderResponse.model_validate(order),
    )


def _details_response(details: WorkOrderDetails) -> WorkOrderDetailsResponse:
    base = WorkOrderResponse.model_validate(details.order)
    total = sum((item.quantity * item.unit_cost for item in details.cost_items), Decimal("0.00"))
    return WorkOrderDetailsResponse(
        **base.model_dump(),
        notes=[WorkOrderNoteResponse.model_validate(note) for note in details.notes],
        cost_items=[WorkOrderCostItemResponse.model_validate(item) for item in details.cost_items],
        total_cost=total,
    )


def _raise_work_order_error(exc: Exception) -> NoReturn:
    if isinstance(exc, WorkOrderNotFoundError):
        raise APIError(
            status_code=404,
            code="WORK_ORDER_NOT_FOUND",
            message="The requested work order was not found.",
        ) from exc
    if isinstance(exc, WorkOrderMechanicNotFoundError):
        raise APIError(
            status_code=404,
            code="MECHANIC_NOT_FOUND",
            message="The requested active mechanic was not found.",
        ) from exc
    if isinstance(exc, WorkOrderSourceNotFoundError):
        raise APIError(
            status_code=404,
            code="WORK_ORDER_SOURCE_NOT_FOUND",
            message="The requested defect or maintenance schedule was not found.",
        ) from exc
    if isinstance(exc, WorkOrderPermissionError):
        raise APIError(
            status_code=403,
            code="WORK_ORDER_ACTION_FORBIDDEN",
            message="This role cannot perform the requested work-order action.",
        ) from exc
    if isinstance(exc, WorkOrderStaleVersionError):
        raise APIError(
            status_code=409,
            code="STALE_VERSION",
            message="The work order was changed by another user.",
        ) from exc
    if isinstance(exc, WorkOrderSourceConflictError):
        raise APIError(
            status_code=409,
            code="WORK_ORDER_ALREADY_EXISTS",
            message="A work order already exists for this source record.",
        ) from exc
    if isinstance(exc, WorkOrderInvalidTransitionError):
        raise APIError(
            status_code=409,
            code="INVALID_WORK_ORDER_TRANSITION",
            message="The requested work-order transition is not allowed.",
        ) from exc
    if isinstance(exc, WorkOrderClosedError):
        raise APIError(
            status_code=409,
            code="WORK_ORDER_CLOSED",
            message="The work order no longer accepts this change.",
        ) from exc
    if isinstance(exc, WorkOrderVerificationNoteRequiredError):
        raise APIError(
            status_code=422,
            code="VERIFICATION_NOTE_REQUIRED",
            message="A verification note is required to verify the repair.",
        ) from exc
    raise exc
