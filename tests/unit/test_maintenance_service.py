from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from fleetpulse.maintenance.exceptions import InvalidMaintenanceRuleError
from fleetpulse.maintenance.service import (
    DUE_SOON_DAYS,
    DUE_SOON_KM,
    calculate_schedule_status,
    validate_rule_intervals,
)
from fleetpulse.maintenance.types import MaintenanceScheduleStatus

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
