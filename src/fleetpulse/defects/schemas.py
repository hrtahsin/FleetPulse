from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from fleetpulse.defects.types import DefectSeverity, DefectStatus


class DefectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    inspection_id: UUID
    inspection_response_id: UUID | None
    vehicle_id: UUID
    category: str
    description: str
    severity: DefectSeverity
    status: DefectStatus
    reported_by_user_id: UUID
    resolved_at: datetime | None
    resolution_note: str | None
    created_at: datetime
    updated_at: datetime


class DefectListResponse(BaseModel):
    items: list[DefectResponse]


class DefectUpdateRequest(BaseModel):
    status: DefectStatus
    resolution_note: str | None = Field(default=None, min_length=3, max_length=2000)

    @model_validator(mode="after")
    def require_dismissal_note(self) -> "DefectUpdateRequest":
        if self.status is DefectStatus.DISMISSED and not self.resolution_note:
            raise ValueError("A resolution note is required when dismissing a defect")
        return self
