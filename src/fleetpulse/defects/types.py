from enum import StrEnum


class DefectSeverity(StrEnum):
    MINOR = "minor"
    MAJOR = "major"
    CRITICAL = "critical"


class DefectStatus(StrEnum):
    OPEN = "open"
    TRIAGED = "triaged"
    IN_REPAIR = "in_repair"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"
