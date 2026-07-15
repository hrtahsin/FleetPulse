from datetime import datetime
from decimal import Decimal
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from fleetpulse.work_orders.types import WorkOrderCostKind, WorkOrderPriority, WorkOrderStatus


class WorkOrderCreateRequest(BaseModel):
    source_defect_id: UUID | None = None
    maintenance_schedule_id: UUID | None = None
    title: str = Field(min_length=1, max_length=180)
    description: str = Field(min_length=1, max_length=5000)
    priority: WorkOrderPriority = WorkOrderPriority.NORMAL
    assigned_mechanic_membership_id: UUID | None = None

    @field_validator("title", "description", mode="before")
    @classmethod
    def strip_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def require_one_source(self) -> Self:
        if (self.source_defect_id is None) == (self.maintenance_schedule_id is None):
            raise ValueError("Exactly one work-order source is required.")
        return self


class DefectWorkOrderCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=180)
    description: str = Field(min_length=1, max_length=5000)
    priority: WorkOrderPriority = WorkOrderPriority.NORMAL
    assigned_mechanic_membership_id: UUID | None = None

    @field_validator("title", "description", mode="before")
    @classmethod
    def strip_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class WorkOrderUpdateRequest(BaseModel):
    version: int = Field(ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=180)
    description: str | None = Field(default=None, min_length=1, max_length=5000)
    priority: WorkOrderPriority | None = None
    assigned_mechanic_membership_id: UUID | None = None

    @field_validator("title", "description", mode="before")
    @classmethod
    def strip_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def require_change(self) -> Self:
        if not (self.model_fields_set - {"version"}):
            raise ValueError("At least one work-order field is required.")
        return self

    def changes(self) -> dict[str, object]:
        return {
            field: getattr(self, field) for field in self.model_fields_set if field != "version"
        }


class WorkOrderTransitionRequest(BaseModel):
    version: int = Field(ge=1)
    status: WorkOrderStatus
    note: str | None = Field(default=None, max_length=5000)

    @field_validator("note", mode="before")
    @classmethod
    def strip_note(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class WorkOrderNoteCreateRequest(BaseModel):
    body: str = Field(min_length=1, max_length=5000)

    @field_validator("body", mode="before")
    @classmethod
    def strip_body(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class WorkOrderCostItemCreateRequest(BaseModel):
    version: int = Field(ge=1)
    kind: WorkOrderCostKind
    description: str = Field(min_length=1, max_length=180)
    quantity: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    unit_cost: Decimal = Field(ge=0, max_digits=12, decimal_places=2)

    @field_validator("description", mode="before")
    @classmethod
    def strip_description(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class WorkOrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    number: int
    vehicle_id: UUID
    source_defect_id: UUID | None
    maintenance_schedule_id: UUID | None
    title: str
    description: str
    priority: WorkOrderPriority
    status: WorkOrderStatus
    assigned_mechanic_membership_id: UUID | None
    labour_hours: Decimal
    labour_cost: Decimal
    parts_cost: Decimal
    currency: str
    opened_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    closed_at: datetime | None
    version: int
    created_by_user_id: UUID
    created_at: datetime
    updated_at: datetime


class WorkOrderListResponse(BaseModel):
    items: list[WorkOrderResponse]


class WorkOrderNoteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    author_user_id: UUID
    body: str
    created_at: datetime


class WorkOrderCostItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    kind: WorkOrderCostKind
    description: str
    quantity: Decimal
    unit_cost: Decimal
    created_at: datetime


class WorkOrderDetailsResponse(WorkOrderResponse):
    notes: list[WorkOrderNoteResponse]
    cost_items: list[WorkOrderCostItemResponse]
    total_cost: Decimal


class WorkOrderCostItemResultResponse(BaseModel):
    item: WorkOrderCostItemResponse
    work_order: WorkOrderResponse
