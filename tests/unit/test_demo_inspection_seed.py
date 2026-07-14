from decimal import Decimal

from scripts.seed_demo import (
    DEMO_INSPECTION_ITEMS,
    DEMO_INSPECTION_TEMPLATE,
    DEMO_MAINTENANCE_RULES,
)


def test_demo_pre_shift_template_has_unique_ordered_safety_items() -> None:
    codes = [item[0] for item in DEMO_INSPECTION_ITEMS]

    assert DEMO_INSPECTION_TEMPLATE == "Pre-shift safety inspection"
    assert len(codes) == 12
    assert len(set(codes)) == len(codes)
    assert {"service_brakes", "tires_wheels", "steering", "seat_belts"} <= set(codes)


def test_demo_maintenance_rules_cover_date_and_odometer_intervals() -> None:
    assert (
        ("Engine oil service", Decimal("10000.0"), 180),
        ("Annual safety service", None, 365),
    ) == DEMO_MAINTENANCE_RULES
