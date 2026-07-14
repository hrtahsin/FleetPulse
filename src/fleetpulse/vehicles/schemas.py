from datetime import datetime
from decimal import Decimal
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from fleetpulse.vehicles.status import VehicleStatus

VIN_PATTERN = r"^[A-HJ-NPR-Z0-9]{17}$"


class VehicleCreateRequest(BaseModel):
    unit_number: str = Field(min_length=1, max_length=40)
    vin: str | None = Field(default=None, pattern=VIN_PATTERN)
    registration: str | None = Field(default=None, max_length=40)
    make: str = Field(min_length=1, max_length=80)
    model: str = Field(min_length=1, max_length=80)
    model_year: int = Field(ge=1886, le=2100)
    fuel_type: str | None = Field(default=None, max_length=30)
    odometer_km: Decimal = Field(default=Decimal("0.0"), ge=0, decimal_places=1)
    status: VehicleStatus = VehicleStatus.AVAILABLE

    @field_validator("unit_number", "registration", "make", "model", "fuel_type", mode="before")
    @classmethod
    def strip_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("vin", mode="before")
    @classmethod
    def normalize_vin(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value


class VehicleUpdateRequest(BaseModel):
    version: int = Field(ge=1)
    unit_number: str | None = Field(default=None, min_length=1, max_length=40)
    vin: str | None = Field(default=None, pattern=VIN_PATTERN)
    registration: str | None = Field(default=None, max_length=40)
    make: str | None = Field(default=None, min_length=1, max_length=80)
    model: str | None = Field(default=None, min_length=1, max_length=80)
    model_year: int | None = Field(default=None, ge=1886, le=2100)
    fuel_type: str | None = Field(default=None, max_length=30)
    odometer_km: Decimal | None = Field(default=None, ge=0, decimal_places=1)
    status: VehicleStatus | None = None
    status_reason: str | None = Field(default=None, min_length=1, max_length=80)

    @field_validator(
        "unit_number", "registration", "make", "model", "fuel_type", "status_reason", mode="before"
    )
    @classmethod
    def strip_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("vin", mode="before")
    @classmethod
    def normalize_vin(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value

    @model_validator(mode="after")
    def require_change(self) -> Self:
        mutable_fields = self.model_fields_set - {"version", "status_reason"}
        if not mutable_fields:
            raise ValueError("At least one vehicle field must be supplied.")
        non_nullable = {
            "unit_number",
            "make",
            "model",
            "model_year",
            "odometer_km",
            "status",
        }
        if any(getattr(self, field) is None for field in mutable_fields & non_nullable):
            raise ValueError("Required vehicle fields cannot be null.")
        return self

    def changes(self) -> dict[str, object]:
        excluded = {"version", "status_reason"}
        return {field: getattr(self, field) for field in self.model_fields_set - excluded}


class VehicleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    unit_number: str
    vin: str | None
    registration: str | None
    make: str
    model: str
    model_year: int
    fuel_type: str | None
    odometer_km: Decimal
    status: VehicleStatus
    version: int
    created_at: datetime
    updated_at: datetime
    retired_at: datetime | None


class VehicleListResponse(BaseModel):
    items: list[VehicleResponse]
    next_cursor: str | None


class VehicleStatusHistoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    vehicle_id: UUID
    from_status: VehicleStatus | None
    to_status: VehicleStatus
    reason_code: str
    reason_reference_id: UUID | None
    changed_by_user_id: UUID | None
    created_at: datetime


class VehicleHistoryListResponse(BaseModel):
    items: list[VehicleStatusHistoryResponse]
