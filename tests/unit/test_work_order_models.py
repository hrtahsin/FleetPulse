from fleetpulse.work_orders.models import WorkOrder, WorkOrderCostItem, WorkOrderNote


def test_work_order_tables_keep_tenant_first_operational_indexes() -> None:
    order_indexes = {index.name for index in WorkOrder.__table__.indexes}
    note_indexes = {index.name for index in WorkOrderNote.__table__.indexes}
    cost_indexes = {index.name for index in WorkOrderCostItem.__table__.indexes}

    assert "ix_work_orders_org_status_mechanic" in order_indexes
    assert "ix_work_orders_org_vehicle" in order_indexes
    assert "ix_work_order_notes_org_order_created" in note_indexes
    assert "ix_work_order_cost_items_org_order" in cost_indexes


def test_work_order_number_and_sources_are_unique() -> None:
    unique_columns = {
        tuple(column.name for column in constraint.columns)
        for constraint in WorkOrder.__table__.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }

    assert ("organization_id", "number") in unique_columns
    assert ("source_defect_id",) in unique_columns
    assert ("maintenance_schedule_id",) in unique_columns
