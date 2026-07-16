from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class AuditActorResponse(BaseModel):
    id: UUID
    display_name: str
    email: str


class AuditEventResponse(BaseModel):
    id: UUID
    action: str
    entity_type: str
    entity_id: UUID | None
    actor: AuditActorResponse | None
    before_data: dict[str, Any] | None
    after_data: dict[str, Any] | None
    request_id: UUID | None
    created_at: datetime


class AuditEventListResponse(BaseModel):
    items: list[AuditEventResponse]
