from fleetpulse.shared.models import Base
from fleetpulse.vehicles.models import Vehicle, VehicleAssignment, VehicleStatusHistory
from fleetpulse.vehicles.status import VehicleStatus


def test_vehicle_tables_are_registered_with_tenant_columns() -> None:
    tables = Base.metadata.tables

    assert {"vehicles", "vehicle_assignments", "vehicle_status_history"} <= tables.keys()
    assert "organization_id" in tables["vehicles"].columns
    assert "organization_id" in tables["vehicle_assignments"].columns
    assert "organization_id" in tables["vehicle_status_history"].columns


def test_vehicle_models_use_the_complete_operational_status_set() -> None:
    assert {status.value for status in VehicleStatus} == {
        "available",
        "in_service",
        "maintenance_due",
        "under_repair",
        "out_of_service",
        "retired",
    }
    assert Vehicle.__tablename__ == "vehicles"
    assert VehicleAssignment.__tablename__ == "vehicle_assignments"
    assert VehicleStatusHistory.__tablename__ == "vehicle_status_history"
