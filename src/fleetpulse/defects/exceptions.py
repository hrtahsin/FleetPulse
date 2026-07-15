class DefectNotFoundError(Exception):
    pass


class InvalidDefectTransitionError(Exception):
    """The requested status change is not allowed."""


class DefectHasActiveWorkOrderError(Exception):
    """An active work order prevents dismissing the defect."""
