class InspectionError(Exception):
    """Base exception for inspection workflow failures."""


class InspectionNotFoundError(InspectionError):
    pass


class InspectionTemplateNotFoundError(InspectionError):
    pass


class InspectionVehicleNotFoundError(InspectionError):
    pass


class VehicleNotInspectableError(InspectionError):
    pass


class InspectionOdometerRollbackError(InspectionError):
    pass


class InvalidInspectionResponseError(InspectionError):
    pass


class MissingInspectionResponseError(InspectionError):
    pass


class IdempotencyPayloadMismatchError(InspectionError):
    pass
