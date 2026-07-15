import uuid
from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from fleetpulse.audit.schemas import (
    AuditActorResponse,
    AuditEventListResponse,
    AuditEventResponse,
)
from fleetpulse.audit.service import AuditService
from fleetpulse.auth.dependencies import require_roles
from fleetpulse.auth.roles import MembershipRole
from fleetpulse.auth.service import CurrentIdentity

router = APIRouter(prefix="/audit-events", tags=["audit"])
audit_reader = require_roles(MembershipRole.OWNER, MembershipRole.MANAGER)


@lru_cache
def get_audit_service() -> AuditService:
    return AuditService()


@router.get("", response_model=AuditEventListResponse)
async def list_audit_events(
    identity: Annotated[CurrentIdentity, Depends(audit_reader)],
    service: Annotated[AuditService, Depends(get_audit_service)],
    entity_type: Annotated[str | None, Query(min_length=1, max_length=80)] = None,
    entity_id: uuid.UUID | None = None,
    action: Annotated[str | None, Query(min_length=1, max_length=100)] = None,
    actor_user_id: uuid.UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> AuditEventListResponse:
    records = await service.list(
        organization_id=identity.organization_id,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        actor_user_id=actor_user_id,
        limit=limit,
    )
    return AuditEventListResponse(
        items=[
            AuditEventResponse(
                id=record.event.id,
                action=record.event.action,
                entity_type=record.event.entity_type,
                entity_id=record.event.entity_id,
                actor=(
                    AuditActorResponse(
                        id=record.actor.id,
                        display_name=record.actor.display_name,
                        email=record.actor.email,
                    )
                    if record.actor
                    else None
                ),
                before_data=record.event.before_data,
                after_data=record.event.after_data,
                request_id=record.event.request_id,
                created_at=record.event.created_at,
            )
            for record in records
        ]
    )
