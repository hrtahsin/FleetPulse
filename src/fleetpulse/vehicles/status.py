from enum import StrEnum


class VehicleStatus(StrEnum):
    AVAILABLE = "available"
    IN_SERVICE = "in_service"
    MAINTENANCE_DUE = "maintenance_due"
    UNDER_REPAIR = "under_repair"
    OUT_OF_SERVICE = "out_of_service"
    RETIRED = "retired"


ACTIVE_VEHICLE_STATUSES = frozenset(VehicleStatus) - {VehicleStatus.RETIRED}
