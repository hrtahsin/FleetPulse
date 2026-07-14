from apps.worker.celery_app import celery_app


def test_daily_maintenance_evaluation_is_registered() -> None:
    schedule = celery_app.conf.beat_schedule["daily-maintenance-evaluation"]

    assert schedule["task"] == "maintenance.evaluate_schedules"
    assert str(schedule["schedule"]) == "<crontab: 0 5 * * * (m/h/dM/MY/d)>"
