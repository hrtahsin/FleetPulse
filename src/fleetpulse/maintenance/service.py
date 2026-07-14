import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fleetpulse.audit.models import AuditEvent
from fleetpulse.maintenance.exceptions import (
    InvalidMaintenanceRuleError,
    MaintenanceRuleNotFoundError,
    MaintenanceVehicleNotFoundError,
)
from fleetpulse.maintenance.models import MaintenanceRule, MaintenanceSchedule
from fleetpulse.maintenance.repository import MaintenanceRepository
from fleetpulse.maintenance.types import MaintenanceScheduleStatus
from fleetpulse.notifications.models import Notification
from fleetpulse.outbox.models import OutboxEvent
from fleetpulse.shared.database import get_session_factory
from fleetpulse.vehicles.models import Vehicle

DUE_SOON_DAYS = 30
DUE_SOON_KM = Decimal("1000.0")


@dataclass(frozen=True, slots=True)
class CreateMaintenanceRule:
    name: str
    vehicle_id: uuid.UUID | None
    interval_km: Decimal | None
    interval_days: int | None
    active: bool = True


@dataclass(frozen=True, slots=True)
class EvaluationResult:
    created: int
    updated: int
    due: int
    overdue: int
    schedules: Sequence[MaintenanceSchedule]


class MaintenanceService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._session_factory = session_factory or get_session_factory()
        self._clock = clock or (lambda: datetime.now(UTC))

    async def list_rules(self, organization_id: uuid.UUID) -> Sequence[MaintenanceRule]:
        async with self._session_factory() as session:
            return await MaintenanceRepository(session).list_rules(organization_id)

    async def create_rule(
        self,
        *,
        organization_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        request_id: uuid.UUID,
        data: CreateMaintenanceRule,
    ) -> MaintenanceRule:
        validate_rule_intervals(data.interval_km, data.interval_days)
        now = self._clock()
        async with self._session_factory() as session, session.begin():
            repository = MaintenanceRepository(session)
            await self._validate_vehicle(repository, organization_id, data.vehicle_id)
            rule = MaintenanceRule(
                id=uuid.uuid4(),
                organization_id=organization_id,
                name=data.name,
                vehicle_id=data.vehicle_id,
                interval_km=data.interval_km,
                interval_days=data.interval_days,
                active=data.active,
                created_at=now,
                updated_at=now,
            )
            repository.add(
                rule,
                self._audit(
                    organization_id=organization_id,
                    actor_user_id=actor_user_id,
                    action="maintenance_rule.created",
                    entity_type="maintenance_rule",
                    entity_id=rule.id,
                    request_id=request_id,
                    after_data=rule_snapshot(rule),
                    now=now,
                ),
                self._event(
                    event_type="maintenance_rule.created.v1",
                    organization_id=organization_id,
                    aggregate_type="maintenance_rule",
                    aggregate_id=rule.id,
                    actor_user_id=actor_user_id,
                    correlation_id=request_id,
                    data=rule_snapshot(rule),
                    now=now,
                ),
            )
        return rule

    async def update_rule(
        self,
        *,
        organization_id: uuid.UUID,
        rule_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        request_id: uuid.UUID,
        changes: Mapping[str, object],
    ) -> MaintenanceRule:
        now = self._clock()
        async with self._session_factory() as session, session.begin():
            repository = MaintenanceRepository(session)
            rule = await repository.get_rule(organization_id, rule_id)
            if rule is None:
                raise MaintenanceRuleNotFoundError
            before = rule_snapshot(rule)
            vehicle_id = changes.get("vehicle_id", rule.vehicle_id)
            if vehicle_id is not None and not isinstance(vehicle_id, uuid.UUID):
                vehicle_id = uuid.UUID(str(vehicle_id))
            interval_km_value = changes.get("interval_km", rule.interval_km)
            interval_km = Decimal(str(interval_km_value)) if interval_km_value is not None else None
            interval_days_value = changes.get("interval_days", rule.interval_days)
            interval_days = (
                interval_days_value
                if isinstance(interval_days_value, int)
                else int(str(interval_days_value))
                if interval_days_value is not None
                else None
            )
            validate_rule_intervals(interval_km, interval_days)
            await self._validate_vehicle(repository, organization_id, vehicle_id)

            for field in {"name", "active"} & changes.keys():
                setattr(rule, field, changes[field])
            rule.vehicle_id = vehicle_id
            rule.interval_km = interval_km
            rule.interval_days = interval_days
            rule.updated_at = now
            repository.add(
                self._audit(
                    organization_id=organization_id,
                    actor_user_id=actor_user_id,
                    action="maintenance_rule.updated",
                    entity_type="maintenance_rule",
                    entity_id=rule.id,
                    request_id=request_id,
                    before_data=before,
                    after_data=rule_snapshot(rule),
                    now=now,
                )
            )
        return rule

    async def list_schedules(
        self,
        organization_id: uuid.UUID,
        *,
        status: MaintenanceScheduleStatus | None,
    ) -> Sequence[MaintenanceSchedule]:
        async with self._session_factory() as session:
            return await MaintenanceRepository(session).list_schedules(
                organization_id, status=status
            )

    async def evaluate(
        self,
        *,
        organization_id: uuid.UUID,
        actor_user_id: uuid.UUID | None,
        request_id: uuid.UUID,
    ) -> EvaluationResult:
        now = self._clock()
        async with self._session_factory() as session, session.begin():
            repository = MaintenanceRepository(session)
            rules = await repository.list_active_rules(organization_id)
            vehicles = await repository.list_eligible_vehicles(organization_id)
            schedules = {
                (schedule.vehicle_id, schedule.maintenance_rule_id): schedule
                for schedule in await repository.list_all_schedules(organization_id)
            }
            recipients = await repository.management_user_ids(organization_id)
            created = 0
            updated = 0
            changed_due: list[MaintenanceSchedule] = []

            for rule in rules:
                targets = (
                    [vehicle for vehicle in vehicles if vehicle.id == rule.vehicle_id]
                    if rule.vehicle_id is not None
                    else vehicles
                )
                for vehicle in targets:
                    key = (vehicle.id, rule.id)
                    schedule = schedules.get(key)
                    previous_status = schedule.status if schedule is not None else None
                    due_at, due_odometer = calculate_due_thresholds(rule, vehicle, schedule)
                    next_status = calculate_schedule_status(
                        now=now,
                        vehicle_odometer_km=vehicle.odometer_km,
                        due_at=due_at,
                        due_odometer_km=due_odometer,
                    )
                    if schedule is None:
                        schedule = MaintenanceSchedule(
                            id=uuid.uuid4(),
                            organization_id=organization_id,
                            vehicle_id=vehicle.id,
                            maintenance_rule_id=rule.id,
                            due_at=due_at,
                            due_odometer_km=due_odometer,
                            status=next_status,
                            evaluated_at=now,
                            created_at=now,
                            updated_at=now,
                        )
                        repository.add(schedule)
                        schedules[key] = schedule
                        created += 1
                    else:
                        schedule.due_at = due_at
                        schedule.due_odometer_km = due_odometer
                        schedule.status = next_status
                        schedule.evaluated_at = now
                        schedule.updated_at = now
                        updated += 1
                    if previous_status != next_status and next_status in {
                        MaintenanceScheduleStatus.DUE,
                        MaintenanceScheduleStatus.OVERDUE,
                    }:
                        changed_due.append(schedule)

            for schedule in changed_due:
                repository.add(
                    self._audit(
                        organization_id=organization_id,
                        actor_user_id=actor_user_id,
                        action="maintenance.became_due",
                        entity_type="maintenance_schedule",
                        entity_id=schedule.id,
                        request_id=request_id,
                        after_data={
                            "vehicle_id": str(schedule.vehicle_id),
                            "status": schedule.status.value,
                        },
                        now=now,
                    ),
                    self._event(
                        event_type="maintenance.became_due.v1",
                        organization_id=organization_id,
                        aggregate_type="maintenance_schedule",
                        aggregate_id=schedule.id,
                        actor_user_id=actor_user_id,
                        correlation_id=request_id,
                        data={
                            "vehicle_id": str(schedule.vehicle_id),
                            "status": schedule.status.value,
                        },
                        now=now,
                    ),
                )
                for recipient_user_id in recipients:
                    repository.add(
                        Notification(
                            id=uuid.uuid4(),
                            organization_id=organization_id,
                            recipient_user_id=recipient_user_id,
                            type="maintenance_due",
                            title="Vehicle maintenance requires attention",
                            body=f"Schedule status changed to {schedule.status.value}.",
                            entity_type="maintenance_schedule",
                            entity_id=schedule.id,
                            created_at=now,
                        )
                    )

            ordered = sorted(
                schedules.values(),
                key=lambda item: (
                    item.status.value,
                    item.due_at or datetime.max.replace(tzinfo=UTC),
                ),
            )
            return EvaluationResult(
                created=created,
                updated=updated,
                due=sum(item.status == MaintenanceScheduleStatus.DUE for item in ordered),
                overdue=sum(item.status == MaintenanceScheduleStatus.OVERDUE for item in ordered),
                schedules=ordered,
            )

    @staticmethod
    async def _validate_vehicle(
        repository: MaintenanceRepository,
        organization_id: uuid.UUID,
        vehicle_id: uuid.UUID | None,
    ) -> None:
        if (
            vehicle_id is not None
            and await repository.get_vehicle(organization_id, vehicle_id) is None
        ):
            raise MaintenanceVehicleNotFoundError

    @staticmethod
    def _audit(
        *,
        organization_id: uuid.UUID,
        actor_user_id: uuid.UUID | None,
        action: str,
        entity_type: str,
        entity_id: uuid.UUID,
        request_id: uuid.UUID,
        now: datetime,
        before_data: dict[str, object] | None = None,
        after_data: dict[str, object] | None = None,
    ) -> AuditEvent:
        return AuditEvent(
            id=uuid.uuid4(),
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            before_data=before_data,
            after_data=after_data,
            request_id=request_id,
            created_at=now,
        )

    @staticmethod
    def _event(
        *,
        event_type: str,
        organization_id: uuid.UUID,
        aggregate_type: str,
        aggregate_id: uuid.UUID,
        actor_user_id: uuid.UUID | None,
        correlation_id: uuid.UUID,
        data: Mapping[str, object],
        now: datetime,
    ) -> OutboxEvent:
        event_id = uuid.uuid4()
        return OutboxEvent(
            id=event_id,
            organization_id=organization_id,
            event_type=event_type,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            payload={
                "event_id": str(event_id),
                "event_type": event_type,
                "occurred_at": now.isoformat(),
                "organization_id": str(organization_id),
                "aggregate": {"type": aggregate_type, "id": str(aggregate_id)},
                "actor_user_id": str(actor_user_id) if actor_user_id else None,
                "correlation_id": str(correlation_id),
                "data": dict(data),
            },
            occurred_at=now,
            attempts=0,
        )


def validate_rule_intervals(interval_km: Decimal | None, interval_days: int | None) -> None:
    if interval_km is None and interval_days is None:
        raise InvalidMaintenanceRuleError
    if interval_km is not None and interval_km <= 0:
        raise InvalidMaintenanceRuleError
    if interval_days is not None and interval_days <= 0:
        raise InvalidMaintenanceRuleError


def calculate_due_thresholds(
    rule: MaintenanceRule,
    vehicle: Vehicle,
    schedule: MaintenanceSchedule | None,
) -> tuple[datetime | None, Decimal | None]:
    base_at = schedule.last_completed_at if schedule else None
    base_odometer = schedule.last_completed_odometer_km if schedule else None
    due_at = (
        (base_at or vehicle.created_at) + timedelta(days=rule.interval_days)
        if rule.interval_days is not None
        else None
    )
    due_odometer = (
        (base_odometer or Decimal("0.0")) + rule.interval_km
        if rule.interval_km is not None
        else None
    )
    return due_at, due_odometer


def calculate_schedule_status(
    *,
    now: datetime,
    vehicle_odometer_km: Decimal,
    due_at: datetime | None,
    due_odometer_km: Decimal | None,
) -> MaintenanceScheduleStatus:
    if (due_at is not None and now > due_at) or (
        due_odometer_km is not None and vehicle_odometer_km > due_odometer_km
    ):
        return MaintenanceScheduleStatus.OVERDUE
    if (due_at is not None and now + timedelta(days=DUE_SOON_DAYS) >= due_at) or (
        due_odometer_km is not None and vehicle_odometer_km + DUE_SOON_KM >= due_odometer_km
    ):
        return MaintenanceScheduleStatus.DUE
    return MaintenanceScheduleStatus.UPCOMING


def rule_snapshot(rule: MaintenanceRule) -> dict[str, object]:
    return {
        "name": rule.name,
        "vehicle_id": str(rule.vehicle_id) if rule.vehicle_id else None,
        "interval_km": str(rule.interval_km) if rule.interval_km is not None else None,
        "interval_days": rule.interval_days,
        "active": rule.active,
    }
