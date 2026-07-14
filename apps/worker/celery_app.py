from celery import Celery
from celery.schedules import crontab

from fleetpulse.shared.config import get_settings

settings = get_settings()
celery_app = Celery(
    "fleetpulse",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["apps.worker.maintenance_tasks"],
)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    beat_schedule={
        "daily-maintenance-evaluation": {
            "task": "maintenance.evaluate_schedules",
            "schedule": crontab(hour=5, minute=0),
        }
    },
)
