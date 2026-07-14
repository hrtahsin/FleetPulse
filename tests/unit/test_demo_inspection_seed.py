from scripts.seed_demo import DEMO_INSPECTION_ITEMS, DEMO_INSPECTION_TEMPLATE


def test_demo_pre_shift_template_has_unique_ordered_safety_items() -> None:
    codes = [item[0] for item in DEMO_INSPECTION_ITEMS]

    assert DEMO_INSPECTION_TEMPLATE == "Pre-shift safety inspection"
    assert len(codes) == 12
    assert len(set(codes)) == len(codes)
    assert {"service_brakes", "tires_wheels", "steering", "seat_belts"} <= set(codes)
