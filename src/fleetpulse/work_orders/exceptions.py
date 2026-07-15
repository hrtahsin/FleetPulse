class WorkOrderError(Exception):
    """Base work-order domain error."""


class WorkOrderNotFoundError(WorkOrderError):
    pass


class WorkOrderSourceNotFoundError(WorkOrderError):
    pass


class WorkOrderSourceConflictError(WorkOrderError):
    pass


class WorkOrderMechanicNotFoundError(WorkOrderError):
    pass


class WorkOrderInvalidTransitionError(WorkOrderError):
    pass


class WorkOrderStaleVersionError(WorkOrderError):
    pass


class WorkOrderPermissionError(WorkOrderError):
    pass


class WorkOrderClosedError(WorkOrderError):
    pass


class WorkOrderVerificationNoteRequiredError(WorkOrderError):
    pass
