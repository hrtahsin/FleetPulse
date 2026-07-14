from enum import StrEnum


class ResponseType(StrEnum):
    PASS_FAIL = "pass_fail"
    BOOLEAN = "boolean"
    TEXT = "text"
    NUMBER = "number"


class InspectionStatus(StrEnum):
    SUBMITTED = "submitted"
    REVIEWED = "reviewed"
