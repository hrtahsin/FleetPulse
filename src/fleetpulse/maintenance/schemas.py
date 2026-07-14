from datetime import datetime
from decimal import Decimal
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from fleetpulse.maintenance.types import MaintenanceScheduleStatus


class MaintenanceRuleCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    vehicle_id: UUID | None = None
    interval_km: Decimal | None = Field(default=None, gt=0, decimal_places=1)
    interval_days: int | None = Field(default=None, gt=0, le=3650)
    active: bool = True

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def require_interval(self) -> Self:
        if self.interval_km is None and self.interval_days is None:
            raise ValueError("At least one maintenance interval is required.")
        return self


class MaintenanceRuleUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    vehicle_id: UUID | None = None
    interval_km: Decimal | None = Field(default=None, gt=0, decimal_places=1)
    interval_days: int | None = Field(default=None, gt=0, le=3650)
    active: bool | None = None

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def require_change(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("At least one rule field is required.")
        if "name" in self.model_fields_set and self.name is None:
            raise ValueError("Rule name cannot be null.")
        if "active" in self.model_fields_set and self.active is None:
            raise ValueError("Rule active state cannot be null.")
        return self

    def changes(self) -> dict[str, object]:
        return {field: getattr(self, field) for field in self.model_fields_set}


class MaintenanceRuleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    vehicle_id: UUID | None
    interval_km: Decimal | None
    interval_days: int | None
    active: bool
    created_at: datetime
    updated_at: datetime


class MaintenanceRuleListResponse(BaseModel):
    items: list[MaintenanceRuleResponse]


class MaintenanceScheduleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    vehicle_id: UUID
    maintenance_rule_id: UUID
    last_completed_at: datetime | None
    last_completed_odometer_km: Decimal | None
    due_at: datetime | None
    due_odometer_km: Decimal | None
    status: MaintenanceScheduleStatus
    evaluated_at: datetime
    created_at: datetime
    updated_at: datetime


class MaintenanceScheduleListResponse(BaseModel):
    items: list[MaintenanceScheduleResponse]


class MaintenanceEvaluationResponse(BaseModel):
    created: int
    updated: int
    due: int
    overdue: int
    schedules: list[MaintenanceScheduleResponse]
