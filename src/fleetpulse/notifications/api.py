import uuid
from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from fleetpulse.auth.dependencies import get_current_identity
from fleetpulse.auth.service import CurrentIdentity
from fleetpulse.notifications.exceptions import NotificationNotFoundError
from fleetpulse.notifications.schemas import NotificationListResponse, NotificationResponse
from fleetpulse.notifications.service import NotificationService
from fleetpulse.shared.errors import APIError

router = APIRouter(prefix="/notifications", tags=["notifications"])


@lru_cache
def get_notification_service() -> NotificationService:
    return NotificationService()


@router.get("", response_model=NotificationListResponse)
async def list_notifications(
    identity: Annotated[CurrentIdentity, Depends(get_current_identity)],
    service: Annotated[NotificationService, Depends(get_notification_service)],
    unread_only: bool = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> NotificationListResponse:
    records = await service.list(
        organization_id=identity.organization_id,
        recipient_user_id=identity.user_id,
        unread_only=unread_only,
        limit=limit,
    )
    return NotificationListResponse(
        items=[NotificationResponse.model_validate(record) for record in records],
        unread_count=sum(record.read_at is None for record in records),
    )


@router.post("/{notification_id}/read", response_model=NotificationResponse)
async def mark_notification_read(
    notification_id: uuid.UUID,
    identity: Annotated[CurrentIdentity, Depends(get_current_identity)],
    service: Annotated[NotificationService, Depends(get_notification_service)],
) -> NotificationResponse:
    try:
        record = await service.mark_read(
            organization_id=identity.organization_id,
            recipient_user_id=identity.user_id,
            notification_id=notification_id,
        )
    except NotificationNotFoundError as exc:
        raise APIError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="NOTIFICATION_NOT_FOUND",
            message="The requested notification was not found.",
        ) from exc
    return NotificationResponse.model_validate(record)
