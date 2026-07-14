import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from fleetpulse.maintenance.exceptions import InvalidMaintenanceRuleError
from fleetpulse.maintenance.models import MaintenanceRule, MaintenanceSchedule
from fleetpulse.maintenance.service import (
    DUE_SOON_DAYS,
    DUE_SOON_KM,
    calculate_due_thresholds,
    calculate_schedule_status,
    validate_rule_intervals,
)
from fleetpulse.maintenance.types import MaintenanceScheduleStatus
from fleetpulse.vehicles.models import Vehicle
from fleetpulse.vehicles.status import VehicleStatus

NOW = datetime(2026, 7, 14, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("due_at", "due_odometer", "odometer", "expected"),
    [
        (
            NOW + timedelta(days=DUE_SOON_DAYS + 1),
            Decimal("12000.0"),
            Decimal("10000.0"),
            MaintenanceScheduleStatus.UPCOMING,
        ),
        (
            NOW + timedelta(days=DUE_SOON_DAYS),
            None,
            Decimal("10000.0"),
            MaintenanceScheduleStatus.DUE,
        ),
        (
            None,
            Decimal("10000.0") + DUE_SOON_KM,
            Decimal("10000.0"),
            MaintenanceScheduleStatus.DUE,
        ),
        (
            NOW - timedelta(seconds=1),
            None,
            Decimal("10000.0"),
            MaintenanceScheduleStatus.OVERDUE,
        ),
        (
            None,
            Decimal("9999.9"),
            Decimal("10000.0"),
            MaintenanceScheduleStatus.OVERDUE,
        ),
    ],
)
def test_schedule_status_is_transparent_and_deterministic(
    due_at: datetime | None,
    due_odometer: Decimal | None,
    odometer: Decimal,
    expected: MaintenanceScheduleStatus,
) -> None:
    assert (
        calculate_schedule_status(
            now=NOW,
            vehicle_odometer_km=odometer,
            due_at=due_at,
            due_odometer_km=due_odometer,
        )
        is expected
    )


def test_rule_requires_at_least_one_positive_interval() -> None:
    with pytest.raises(InvalidMaintenanceRuleError):
        validate_rule_intervals(None, None)
    with pytest.raises(InvalidMaintenanceRuleError):
        validate_rule_intervals(Decimal("0"), 30)

    validate_rule_intervals(Decimal("10000.0"), None)
    validate_rule_intervals(None, 90)


def test_initial_thresholds_start_from_current_vehicle_state_and_remain_stable() -> None:
    vehicle = Vehicle(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        unit_number="FP-101",
        make="Ford",
        model="Transit",
        model_year=2024,
        odometer_km=Decimal("42180.0"),
        status=VehicleStatus.AVAILABLE,
        version=1,
        created_at=NOW - timedelta(days=100),
        updated_at=NOW,
    )
    rule = MaintenanceRule(
        id=uuid.uuid4(),
        organization_id=vehicle.organization_id,
        name="Oil and safety service",
        interval_km=Decimal("10000.0"),
        interval_days=180,
        active=True,
        created_at=NOW,
        updated_at=NOW,
    )

    due_at, due_odometer = calculate_due_thresholds(rule, vehicle, None)
    assert due_at == NOW + timedelta(days=180)
    assert due_odometer == Decimal("52180.0")

    schedule = MaintenanceSchedule(
        organization_id=vehicle.organization_id,
        vehicle_id=vehicle.id,
        maintenance_rule_id=rule.id,
        due_at=due_at,
        due_odometer_km=due_odometer,
        status=MaintenanceScheduleStatus.UPCOMING,
        evaluated_at=NOW,
    )
    vehicle.odometer_km = Decimal("43000.0")

    assert calculate_due_thresholds(rule, vehicle, schedule) == (due_at, due_odometer)
