from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class VehicleSummary(BaseModel):
    total: int
    operational: int
    unavailable: int
    available: int
    in_service: int
    maintenance_due: int
    under_repair: int
    out_of_service: int
    retired: int


class DefectSummary(BaseModel):
    active: int
    critical: int
    triaged: int
    in_repair: int


class MaintenanceSummary(BaseModel):
    upcoming: int
    due: int
    overdue: int


class WorkOrderSummary(BaseModel):
    active: int
    unassigned: int
    waiting_parts: int
    awaiting_verification: int
    repair_cost_30_days: Decimal


class DashboardSummaryResponse(BaseModel):
    generated_at: datetime
    currency: str
    vehicles: VehicleSummary
    defects: DefectSummary
    maintenance: MaintenanceSummary
    work_orders: WorkOrderSummary
