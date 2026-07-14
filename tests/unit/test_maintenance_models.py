from fleetpulse.maintenance.models import MaintenanceRule, MaintenanceSchedule


def test_maintenance_tables_keep_tenant_first_operational_indexes() -> None:
    rule_indexes = {index.name for index in MaintenanceRule.__table__.indexes}
    schedule_indexes = {index.name for index in MaintenanceSchedule.__table__.indexes}

    assert "ix_maintenance_rules_org_active" in rule_indexes
    assert "ix_maintenance_rules_org_vehicle" in rule_indexes
    assert "ix_maintenance_schedules_org_status_due" in schedule_indexes
    assert "ix_maintenance_schedules_org_vehicle" in schedule_indexes


def test_schedule_uniqueness_is_vehicle_and_rule_scoped() -> None:
    unique_columns = {
        tuple(column.name for column in constraint.columns)
        for constraint in MaintenanceSchedule.__table__.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }

    assert ("vehicle_id", "maintenance_rule_id") in unique_columns
