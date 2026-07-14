from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from fleetpulse.defects.types import DefectSeverity, DefectStatus
from fleetpulse.inspections.types import InspectionStatus, ResponseType


class InspectionTemplateItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    label: str
    category: str
    response_type: ResponseType
    required: bool
    sort_order: int


class ActiveInspectionTemplateResponse(BaseModel):
    id: UUID
    name: str
    version: int
    items: list[InspectionTemplateItemResponse]


class ReportedDefectRequest(BaseModel):
    category: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=1, max_length=2000)
    severity: DefectSeverity


class SubmittedResponseRequest(BaseModel):
    template_item_id: UUID
    result: str = Field(min_length=1, max_length=500)
    comment: str | None = Field(default=None, max_length=2000)
    defect: ReportedDefectRequest | None = None


class InspectionSubmitRequest(BaseModel):
    vehicle_id: UUID
    template_id: UUID
    odometer_km: Decimal = Field(ge=0, decimal_places=1)
    notes: str | None = Field(default=None, max_length=4000)
    responses: list[SubmittedResponseRequest] = Field(min_length=1, max_length=100)


class DefectSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    inspection_response_id: UUID | None
    category: str
    description: str
    severity: DefectSeverity
    status: DefectStatus
    created_at: datetime


class InspectionResponseRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    template_item_id: UUID
    result: str
    comment: str | None
    defect: DefectSummaryResponse | None = None


class InspectionSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    vehicle_id: UUID
    driver_membership_id: UUID
    template_id: UUID
    odometer_km: Decimal
    status: InspectionStatus
    notes: str | None
    submitted_at: datetime


class InspectionDetailsResponse(InspectionSummaryResponse):
    responses: list[InspectionResponseRecord]
    defects: list[DefectSummaryResponse]
    replayed: bool = False


class InspectionListResponse(BaseModel):
    items: list[InspectionSummaryResponse]
