import asyncio
import uuid

from apps.worker.celery_app import celery_app
from fleetpulse.maintenance.service import MaintenanceService
from fleetpulse.shared.database import dispose_engine


async def evaluate_active_organizations() -> dict[str, int]:
    service = MaintenanceService()
    organizations = await service.organization_ids_with_active_rules()
    evaluated = 0
    created = 0
    updated = 0
    due = 0
    overdue = 0
    try:
        for organization_id in organizations:
            result = await service.evaluate(
                organization_id=organization_id,
                actor_user_id=None,
                request_id=uuid.uuid4(),
            )
            evaluated += 1
            created += result.created
            updated += result.updated
            due += result.due
            overdue += result.overdue
        return {
            "organizations": evaluated,
            "created": created,
            "updated": updated,
            "due": due,
            "overdue": overdue,
        }
    finally:
        await dispose_engine()


@celery_app.task(name="maintenance.evaluate_schedules")  # type: ignore[untyped-decorator]
def evaluate_maintenance_schedules() -> dict[str, int]:
    return asyncio.run(evaluate_active_organizations())
