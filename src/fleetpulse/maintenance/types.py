from enum import StrEnum


class MaintenanceScheduleStatus(StrEnum):
    UPCOMING = "upcoming"
    DUE = "due"
    OVERDUE = "overdue"
    COMPLETED = "completed"
    DISMISSED = "dismissed"
