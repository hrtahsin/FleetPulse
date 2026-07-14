import uuid

import pytest

from fleetpulse.vehicles.exceptions import InvalidVehicleCursorError
from fleetpulse.vehicles.service import LEGAL_STATUS_TRANSITIONS, decode_cursor, encode_cursor
from fleetpulse.vehicles.status import VehicleStatus


def test_vehicle_cursor_round_trips_without_exposing_raw_uuid() -> None:
    vehicle_id = uuid.uuid4()

    cursor = encode_cursor(vehicle_id)

    assert str(vehicle_id) not in cursor
    assert decode_cursor(cursor) == vehicle_id


@pytest.mark.parametrize("cursor", ["not-a-cursor", "", "abcde"])
def test_invalid_vehicle_cursor_is_rejected(cursor: str) -> None:
    with pytest.raises(InvalidVehicleCursorError):
        decode_cursor(cursor)


def test_retired_vehicle_is_terminal() -> None:
    assert LEGAL_STATUS_TRANSITIONS[VehicleStatus.RETIRED] == frozenset()


def test_operational_status_rules_cover_safety_transitions() -> None:
    assert VehicleStatus.OUT_OF_SERVICE in LEGAL_STATUS_TRANSITIONS[VehicleStatus.IN_SERVICE]
    assert VehicleStatus.UNDER_REPAIR in LEGAL_STATUS_TRANSITIONS[VehicleStatus.OUT_OF_SERVICE]
    assert VehicleStatus.RETIRED in LEGAL_STATUS_TRANSITIONS[VehicleStatus.UNDER_REPAIR]
