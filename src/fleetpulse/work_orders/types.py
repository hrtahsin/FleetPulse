from enum import StrEnum


class WorkOrderPriority(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


class WorkOrderStatus(StrEnum):
    REPORTED = "reported"
    TRIAGED = "triaged"
    APPROVED = "approved"
    IN_PROGRESS = "in_progress"
    WAITING_PARTS = "waiting_parts"
    COMPLETED = "completed"
    VERIFIED = "verified"
    CLOSED = "closed"
    CANCELLED = "cancelled"


class WorkOrderCostKind(StrEnum):
    PART = "part"
    LABOUR = "labour"
    OTHER = "other"
