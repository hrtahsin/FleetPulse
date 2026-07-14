class VehicleError(Exception):
    """Base exception for vehicle domain failures."""


class VehicleNotFoundError(VehicleError):
    pass


class DuplicateVehicleError(VehicleError):
    pass


class OdometerRollbackError(VehicleError):
    pass


class InvalidStatusTransitionError(VehicleError):
    pass


class StatusReasonRequiredError(VehicleError):
    pass


class StaleVehicleVersionError(VehicleError):
    pass


class InvalidVehicleCursorError(VehicleError):
    pass
