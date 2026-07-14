import fleetpulse.audit.models  # noqa: F401
import fleetpulse.defects.models  # noqa: F401
import fleetpulse.inspections.models  # noqa: F401
import fleetpulse.notifications.models  # noqa: F401
import fleetpulse.outbox.models  # noqa: F401
from fleetpulse.shared.models import Base


def test_inspection_safety_tables_are_registered() -> None:
    assert {
        "inspection_templates",
        "inspection_template_items",
        "inspections",
        "inspection_responses",
        "defects",
        "notifications",
        "audit_events",
        "outbox_events",
    } <= Base.metadata.tables.keys()


def test_tenant_owned_safety_records_include_organization_id() -> None:
    for table_name in (
        "inspection_templates",
        "inspections",
        "defects",
        "notifications",
        "audit_events",
        "outbox_events",
    ):
        assert "organization_id" in Base.metadata.tables[table_name].columns


def test_inspections_store_payload_hash_for_idempotency() -> None:
    columns = Base.metadata.tables["inspections"].columns

    assert "idempotency_key" in columns
    assert "request_hash" in columns
