import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fleetpulse.audit.models import AuditEvent
from fleetpulse.auth.roles import MANAGEMENT_ROLES, MembershipRole
from fleetpulse.defects.models import Defect
from fleetpulse.defects.types import DefectSeverity, DefectStatus
from fleetpulse.maintenance.models import MaintenanceSchedule
from fleetpulse.maintenance.types import MaintenanceScheduleStatus
from fleetpulse.notifications.models import Notification
from fleetpulse.outbox.models import OutboxEvent
from fleetpulse.shared.database import get_session_factory
from fleetpulse.vehicles.models import VehicleStatusHistory
from fleetpulse.vehicles.status import VehicleStatus
from fleetpulse.work_orders.exceptions import (
    WorkOrderClosedError,
    WorkOrderInvalidTransitionError,
    WorkOrderMechanicNotFoundError,
    WorkOrderNotFoundError,
    WorkOrderPermissionError,
    WorkOrderSourceConflictError,
    WorkOrderSourceNotFoundError,
    WorkOrderStaleVersionError,
    WorkOrderVerificationNoteRequiredError,
)
from fleetpulse.work_orders.models import WorkOrder, WorkOrderCostItem, WorkOrderNote
from fleetpulse.work_orders.repository import WorkOrderRepository
from fleetpulse.work_orders.types import WorkOrderCostKind, WorkOrderPriority, WorkOrderStatus

LEGAL_TRANSITIONS: Mapping[WorkOrderStatus, frozenset[WorkOrderStatus]] = {
    WorkOrderStatus.REPORTED: frozenset({WorkOrderStatus.TRIAGED, WorkOrderStatus.CANCELLED}),
    WorkOrderStatus.TRIAGED: frozenset({WorkOrderStatus.APPROVED, WorkOrderStatus.CANCELLED}),
    WorkOrderStatus.APPROVED: frozenset({WorkOrderStatus.IN_PROGRESS, WorkOrderStatus.CANCELLED}),
    WorkOrderStatus.IN_PROGRESS: frozenset(
        {
            WorkOrderStatus.WAITING_PARTS,
            WorkOrderStatus.COMPLETED,
            WorkOrderStatus.CANCELLED,
        }
    ),
    WorkOrderStatus.WAITING_PARTS: frozenset(
        {
            WorkOrderStatus.IN_PROGRESS,
            WorkOrderStatus.COMPLETED,
            WorkOrderStatus.CANCELLED,
        }
    ),
    WorkOrderStatus.COMPLETED: frozenset({WorkOrderStatus.IN_PROGRESS, WorkOrderStatus.VERIFIED}),
    WorkOrderStatus.VERIFIED: frozenset({WorkOrderStatus.CLOSED}),
    WorkOrderStatus.CLOSED: frozenset(),
    WorkOrderStatus.CANCELLED: frozenset(),
}
MECHANIC_TRANSITIONS = frozenset(
    {
        WorkOrderStatus.IN_PROGRESS,
        WorkOrderStatus.WAITING_PARTS,
        WorkOrderStatus.COMPLETED,
    }
)
TERMINAL_STATUSES = frozenset({WorkOrderStatus.CLOSED, WorkOrderStatus.CANCELLED})


@dataclass(frozen=True, slots=True)
class CreateWorkOrder:
    source_defect_id: uuid.UUID | None
    maintenance_schedule_id: uuid.UUID | None
    title: str
    description: str
    priority: WorkOrderPriority
    assigned_mechanic_membership_id: uuid.UUID | None
    currency: str


@dataclass(frozen=True, slots=True)
class AddCostItem:
    kind: WorkOrderCostKind
    description: str
    quantity: Decimal
    unit_cost: Decimal


@dataclass(frozen=True, slots=True)
class WorkOrderDetails:
    order: WorkOrder
    notes: Sequence[WorkOrderNote]
    cost_items: Sequence[WorkOrderCostItem]


class WorkOrderService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
        clock: Callable[[], datetime] | None = None,
        before_commit: Callable[[], None] | None = None,
    ) -> None:
        self._session_factory = session_factory or get_session_factory()
        self._clock = clock or (lambda: datetime.now(UTC))
        self._before_commit = before_commit

    async def list(
        self,
        *,
        organization_id: uuid.UUID,
        actor_role: MembershipRole,
        actor_membership_id: uuid.UUID,
        status: WorkOrderStatus | None,
        limit: int,
    ) -> Sequence[WorkOrder]:
        assigned = actor_membership_id if actor_role is MembershipRole.MECHANIC else None
        async with self._session_factory() as session:
            return await WorkOrderRepository(session).list_orders(
                organization_id,
                status=status,
                assigned_membership_id=assigned,
                limit=limit,
            )

    async def get(
        self,
        *,
        organization_id: uuid.UUID,
        work_order_id: uuid.UUID,
        actor_role: MembershipRole,
        actor_membership_id: uuid.UUID,
    ) -> WorkOrderDetails:
        async with self._session_factory() as session:
            repository = WorkOrderRepository(session)
            order = await repository.get_order(organization_id, work_order_id)
            self._require_order_access(order, actor_role, actor_membership_id)
            assert order is not None
            return WorkOrderDetails(
                order=order,
                notes=await repository.list_notes(organization_id, order.id),
                cost_items=await repository.list_cost_items(organization_id, order.id),
            )

    async def create(
        self,
        *,
        organization_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        request_id: uuid.UUID,
        data: CreateWorkOrder,
    ) -> WorkOrder:
        if (data.source_defect_id is None) == (data.maintenance_schedule_id is None):
            raise WorkOrderSourceNotFoundError
        now = self._clock()
        try:
            async with self._session_factory() as session, session.begin():
                repository = WorkOrderRepository(session)
                vehicle_id: uuid.UUID
                defect: Defect | None = None
                schedule: MaintenanceSchedule | None = None
                if data.source_defect_id is not None:
                    defect = await repository.get_defect(
                        organization_id, data.source_defect_id, for_update=True
                    )
                    if defect is None or defect.status in {
                        DefectStatus.RESOLVED,
                        DefectStatus.DISMISSED,
                    }:
                        raise WorkOrderSourceNotFoundError
                    vehicle_id = defect.vehicle_id
                else:
                    assert data.maintenance_schedule_id is not None
                    schedule = await repository.get_schedule(
                        organization_id,
                        data.maintenance_schedule_id,
                        for_update=True,
                    )
                    if schedule is None or schedule.status not in {
                        MaintenanceScheduleStatus.DUE,
                        MaintenanceScheduleStatus.OVERDUE,
                    }:
                        raise WorkOrderSourceNotFoundError
                    vehicle_id = schedule.vehicle_id

                mechanic_user_id = await self._validate_mechanic(
                    repository,
                    organization_id,
                    data.assigned_mechanic_membership_id,
                )
                order = WorkOrder(
                    id=uuid.uuid4(),
                    organization_id=organization_id,
                    number=await repository.next_number(organization_id),
                    vehicle_id=vehicle_id,
                    source_defect_id=data.source_defect_id,
                    maintenance_schedule_id=data.maintenance_schedule_id,
                    title=data.title,
                    description=data.description,
                    priority=data.priority,
                    status=WorkOrderStatus.REPORTED,
                    assigned_mechanic_membership_id=data.assigned_mechanic_membership_id,
                    labour_hours=Decimal("0.00"),
                    labour_cost=Decimal("0.00"),
                    parts_cost=Decimal("0.00"),
                    currency=data.currency.upper(),
                    opened_at=now,
                    version=1,
                    created_by_user_id=actor_user_id,
                    created_at=now,
                    updated_at=now,
                )
                if defect is not None:
                    defect.status = DefectStatus.TRIAGED
                repository.add(
                    order,
                    self._audit(
                        organization_id,
                        actor_user_id,
                        "work_order.created",
                        order,
                        request_id,
                        None,
                        order_snapshot(order),
                        now,
                    ),
                    self._event("work_order.created.v1", order, actor_user_id, request_id, now),
                )
                if mechanic_user_id is not None:
                    repository.add(
                        self._notification(
                            organization_id,
                            mechanic_user_id,
                            "work_order_assigned",
                            "Work order assigned",
                            f"Work order #{order.number} is assigned to you.",
                            order.id,
                            now,
                        )
                    )
                self._run_before_commit()
            return order
        except IntegrityError as exc:
            raise WorkOrderSourceConflictError from exc

    async def update(
        self,
        *,
        organization_id: uuid.UUID,
        work_order_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        request_id: uuid.UUID,
        expected_version: int,
        changes: Mapping[str, Any],
    ) -> WorkOrder:
        now = self._clock()
        async with self._session_factory() as session, session.begin():
            repository = WorkOrderRepository(session)
            order = await self._locked_order(
                repository, organization_id, work_order_id, expected_version
            )
            if order.status in TERMINAL_STATUSES:
                raise WorkOrderClosedError
            before = order_snapshot(order)
            if "assigned_mechanic_membership_id" in changes:
                membership_id = changes["assigned_mechanic_membership_id"]
                if membership_id is not None and not isinstance(membership_id, uuid.UUID):
                    membership_id = uuid.UUID(str(membership_id))
                mechanic_user_id = await self._validate_mechanic(
                    repository, organization_id, membership_id
                )
                changed_assignment = membership_id != order.assigned_mechanic_membership_id
                order.assigned_mechanic_membership_id = membership_id
                if changed_assignment and mechanic_user_id is not None:
                    repository.add(
                        self._notification(
                            organization_id,
                            mechanic_user_id,
                            "work_order_assigned",
                            "Work order assigned",
                            f"Work order #{order.number} is assigned to you.",
                            order.id,
                            now,
                        )
                    )
            for field in {"title", "description", "priority"} & changes.keys():
                setattr(order, field, changes[field])
            order.version += 1
            order.updated_at = now
            repository.add(
                self._audit(
                    organization_id,
                    actor_user_id,
                    "work_order.updated",
                    order,
                    request_id,
                    before,
                    order_snapshot(order),
                    now,
                )
            )
            self._run_before_commit()
            return order

    async def transition(
        self,
        *,
        organization_id: uuid.UUID,
        work_order_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        actor_membership_id: uuid.UUID,
        actor_role: MembershipRole,
        request_id: uuid.UUID,
        expected_version: int,
        next_status: WorkOrderStatus,
        note: str | None,
    ) -> WorkOrder:
        now = self._clock()
        async with self._session_factory() as session, session.begin():
            repository = WorkOrderRepository(session)
            order = await self._locked_order(
                repository, organization_id, work_order_id, expected_version
            )
            self._require_transition_access(order, actor_role, actor_membership_id, next_status)
            current = WorkOrderStatus(order.status)
            if next_status not in LEGAL_TRANSITIONS[current]:
                raise WorkOrderInvalidTransitionError
            normalized_note = note.strip() if note else None
            if next_status is WorkOrderStatus.VERIFIED and not normalized_note:
                raise WorkOrderVerificationNoteRequiredError

            before = order_snapshot(order)
            order.status = next_status
            order.version += 1
            order.updated_at = now
            if next_status is WorkOrderStatus.IN_PROGRESS:
                order.started_at = order.started_at or now
                await self._move_vehicle_under_repair(repository, order, actor_user_id, now)
                if order.source_defect_id is not None:
                    defect = await repository.get_defect(
                        organization_id, order.source_defect_id, for_update=True
                    )
                    if defect is not None:
                        defect.status = DefectStatus.IN_REPAIR
            elif next_status is WorkOrderStatus.COMPLETED:
                order.completed_at = now
            elif next_status is WorkOrderStatus.VERIFIED:
                await self._verify_and_reconcile(
                    repository,
                    order,
                    actor_user_id,
                    normalized_note or "",
                    now,
                )
            elif next_status is WorkOrderStatus.CANCELLED:
                order.closed_at = now
                if order.source_defect_id is not None:
                    defect = await repository.get_defect(
                        organization_id, order.source_defect_id, for_update=True
                    )
                    if defect is not None and defect.status in {
                        DefectStatus.TRIAGED,
                        DefectStatus.IN_REPAIR,
                    }:
                        defect.status = DefectStatus.OPEN
                await self._reconcile_vehicle(repository, order, actor_user_id, now)
            elif next_status is WorkOrderStatus.CLOSED:
                order.closed_at = now

            if normalized_note:
                repository.add(
                    WorkOrderNote(
                        id=uuid.uuid4(),
                        organization_id=organization_id,
                        work_order_id=order.id,
                        author_user_id=actor_user_id,
                        body=normalized_note,
                        created_at=now,
                    )
                )
            repository.add(
                self._audit(
                    organization_id,
                    actor_user_id,
                    "work_order.status_changed",
                    order,
                    request_id,
                    before,
                    order_snapshot(order),
                    now,
                ),
                self._event("work_order.status_changed.v1", order, actor_user_id, request_id, now),
            )
            await self._notify_status(repository, order, actor_user_id, now)
            self._run_before_commit()
            return order

    async def add_note(
        self,
        *,
        organization_id: uuid.UUID,
        work_order_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        actor_membership_id: uuid.UUID,
        actor_role: MembershipRole,
        request_id: uuid.UUID,
        body: str,
    ) -> WorkOrderNote:
        now = self._clock()
        async with self._session_factory() as session, session.begin():
            repository = WorkOrderRepository(session)
            order = await repository.get_order(organization_id, work_order_id, for_update=True)
            self._require_order_access(order, actor_role, actor_membership_id)
            assert order is not None
            if order.status in TERMINAL_STATUSES:
                raise WorkOrderClosedError
            note = WorkOrderNote(
                id=uuid.uuid4(),
                organization_id=organization_id,
                work_order_id=order.id,
                author_user_id=actor_user_id,
                body=body,
                created_at=now,
            )
            repository.add(
                note,
                self._audit(
                    organization_id,
                    actor_user_id,
                    "work_order.note_added",
                    order,
                    request_id,
                    None,
                    {"note_id": str(note.id)},
                    now,
                ),
            )
            self._run_before_commit()
            return note

    async def add_cost_item(
        self,
        *,
        organization_id: uuid.UUID,
        work_order_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        actor_membership_id: uuid.UUID,
        actor_role: MembershipRole,
        request_id: uuid.UUID,
        expected_version: int,
        data: AddCostItem,
    ) -> tuple[WorkOrderCostItem, WorkOrder]:
        now = self._clock()
        async with self._session_factory() as session, session.begin():
            repository = WorkOrderRepository(session)
            order = await self._locked_order(
                repository, organization_id, work_order_id, expected_version
            )
            self._require_order_access(order, actor_role, actor_membership_id)
            if order.status in {
                WorkOrderStatus.COMPLETED,
                WorkOrderStatus.VERIFIED,
                WorkOrderStatus.CLOSED,
                WorkOrderStatus.CANCELLED,
            }:
                raise WorkOrderClosedError
            amount = (data.quantity * data.unit_cost).quantize(Decimal("0.01"))
            item = WorkOrderCostItem(
                id=uuid.uuid4(),
                organization_id=organization_id,
                work_order_id=order.id,
                kind=data.kind,
                description=data.description,
                quantity=data.quantity,
                unit_cost=data.unit_cost,
                created_at=now,
            )
            if data.kind is WorkOrderCostKind.LABOUR:
                order.labour_hours += data.quantity
                order.labour_cost += amount
            elif data.kind is WorkOrderCostKind.PART:
                order.parts_cost += amount
            order.version += 1
            order.updated_at = now
            repository.add(
                item,
                self._audit(
                    organization_id,
                    actor_user_id,
                    "work_order.cost_item_added",
                    order,
                    request_id,
                    None,
                    {
                        "cost_item_id": str(item.id),
                        "kind": WorkOrderCostKind(item.kind).value,
                        "amount": str(amount),
                    },
                    now,
                ),
            )
            self._run_before_commit()
            return item, order

    @staticmethod
    async def _validate_mechanic(
        repository: WorkOrderRepository,
        organization_id: uuid.UUID,
        membership_id: uuid.UUID | None,
    ) -> uuid.UUID | None:
        if membership_id is None:
            return None
        record = await repository.get_active_mechanic(organization_id, membership_id)
        if record is None:
            raise WorkOrderMechanicNotFoundError
        return record[1].id

    @staticmethod
    async def _locked_order(
        repository: WorkOrderRepository,
        organization_id: uuid.UUID,
        work_order_id: uuid.UUID,
        expected_version: int,
    ) -> WorkOrder:
        order = await repository.get_order(organization_id, work_order_id, for_update=True)
        if order is None:
            raise WorkOrderNotFoundError
        if order.version != expected_version:
            raise WorkOrderStaleVersionError
        return order

    @staticmethod
    def _require_order_access(
        order: WorkOrder | None,
        actor_role: MembershipRole,
        actor_membership_id: uuid.UUID,
    ) -> None:
        if order is None:
            raise WorkOrderNotFoundError
        if actor_role is MembershipRole.MECHANIC and (
            order.assigned_mechanic_membership_id != actor_membership_id
        ):
            raise WorkOrderNotFoundError
        if actor_role not in MANAGEMENT_ROLES and actor_role is not MembershipRole.MECHANIC:
            raise WorkOrderPermissionError

    @staticmethod
    def _require_transition_access(
        order: WorkOrder,
        actor_role: MembershipRole,
        actor_membership_id: uuid.UUID,
        next_status: WorkOrderStatus,
    ) -> None:
        if actor_role in MANAGEMENT_ROLES:
            return
        if (
            actor_role is not MembershipRole.MECHANIC
            or order.assigned_mechanic_membership_id != actor_membership_id
            or next_status not in MECHANIC_TRANSITIONS
        ):
            raise WorkOrderPermissionError

    @staticmethod
    async def _move_vehicle_under_repair(
        repository: WorkOrderRepository,
        order: WorkOrder,
        actor_user_id: uuid.UUID,
        now: datetime,
    ) -> None:
        vehicle = await repository.get_vehicle(
            order.organization_id, order.vehicle_id, for_update=True
        )
        if vehicle is None or VehicleStatus(vehicle.status) is VehicleStatus.RETIRED:
            raise WorkOrderSourceNotFoundError
        if VehicleStatus(vehicle.status) is not VehicleStatus.UNDER_REPAIR:
            previous = VehicleStatus(vehicle.status)
            vehicle.status = VehicleStatus.UNDER_REPAIR
            vehicle.version += 1
            vehicle.updated_at = now
            repository.add(
                VehicleStatusHistory(
                    id=uuid.uuid4(),
                    organization_id=order.organization_id,
                    vehicle_id=vehicle.id,
                    from_status=previous,
                    to_status=VehicleStatus.UNDER_REPAIR,
                    reason_code=f"work_order_{order.number}_started",
                    changed_by_user_id=actor_user_id,
                    created_at=now,
                )
            )

    async def _verify_and_reconcile(
        self,
        repository: WorkOrderRepository,
        order: WorkOrder,
        actor_user_id: uuid.UUID,
        note: str,
        now: datetime,
    ) -> None:
        if order.source_defect_id is not None:
            defect = await repository.get_defect(
                order.organization_id, order.source_defect_id, for_update=True
            )
            if defect is not None:
                defect.status = DefectStatus.RESOLVED
                defect.resolved_at = now
                defect.resolution_note = note
        if order.maintenance_schedule_id is not None:
            schedule = await repository.get_schedule(
                order.organization_id,
                order.maintenance_schedule_id,
                for_update=True,
            )
            if schedule is not None:
                vehicle = await repository.get_vehicle(
                    order.organization_id, order.vehicle_id, for_update=True
                )
                if vehicle is None:
                    raise WorkOrderSourceNotFoundError
                schedule.status = MaintenanceScheduleStatus.COMPLETED
                schedule.last_completed_at = now
                schedule.last_completed_odometer_km = vehicle.odometer_km
                schedule.evaluated_at = now
                schedule.updated_at = now
        await self._reconcile_vehicle(repository, order, actor_user_id, now)

    async def _reconcile_vehicle(
        self,
        repository: WorkOrderRepository,
        order: WorkOrder,
        actor_user_id: uuid.UUID,
        now: datetime,
    ) -> None:
        vehicle = await repository.get_vehicle(
            order.organization_id, order.vehicle_id, for_update=True
        )
        if vehicle is None:
            raise WorkOrderSourceNotFoundError
        severities = await repository.unresolved_defect_severities(
            order.organization_id, order.vehicle_id
        )
        if DefectSeverity.CRITICAL in severities:
            next_status = VehicleStatus.OUT_OF_SERVICE
        elif await repository.has_active_other_order(
            order.organization_id, order.vehicle_id, order.id
        ):
            next_status = VehicleStatus.UNDER_REPAIR
        elif severities or await repository.has_due_schedule(
            order.organization_id, order.vehicle_id
        ):
            next_status = VehicleStatus.MAINTENANCE_DUE
        else:
            next_status = VehicleStatus.AVAILABLE
        if vehicle.status != next_status:
            previous = VehicleStatus(vehicle.status)
            vehicle.status = next_status
            vehicle.version += 1
            vehicle.updated_at = now
            repository.add(
                VehicleStatusHistory(
                    id=uuid.uuid4(),
                    organization_id=order.organization_id,
                    vehicle_id=vehicle.id,
                    from_status=previous,
                    to_status=next_status,
                    reason_code=f"work_order_{order.number}_verified",
                    changed_by_user_id=actor_user_id,
                    created_at=now,
                )
            )

    @staticmethod
    async def _notify_status(
        repository: WorkOrderRepository,
        order: WorkOrder,
        actor_user_id: uuid.UUID,
        now: datetime,
    ) -> None:
        recipients = set(await repository.management_user_ids(order.organization_id))
        mechanic_user_id = await repository.mechanic_user_id(order.assigned_mechanic_membership_id)
        if mechanic_user_id is not None:
            recipients.add(mechanic_user_id)
        recipients.discard(actor_user_id)
        for user_id in recipients:
            repository.add(
                WorkOrderService._notification(
                    order.organization_id,
                    user_id,
                    "work_order_status",
                    "Work order status changed",
                    f"Work order #{order.number} is now {WorkOrderStatus(order.status).value}.",
                    order.id,
                    now,
                )
            )

    @staticmethod
    def _audit(
        organization_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        action: str,
        order: WorkOrder,
        request_id: uuid.UUID,
        before: dict[str, object] | None,
        after: dict[str, object] | None,
        now: datetime,
    ) -> AuditEvent:
        return AuditEvent(
            id=uuid.uuid4(),
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action=action,
            entity_type="work_order",
            entity_id=order.id,
            before_data=before,
            after_data=after,
            request_id=request_id,
            created_at=now,
        )

    @staticmethod
    def _event(
        event_type: str,
        order: WorkOrder,
        actor_user_id: uuid.UUID,
        request_id: uuid.UUID,
        now: datetime,
    ) -> OutboxEvent:
        event_id = uuid.uuid4()
        return OutboxEvent(
            id=event_id,
            organization_id=order.organization_id,
            event_type=event_type,
            aggregate_type="work_order",
            aggregate_id=order.id,
            payload={
                "event_id": str(event_id),
                "event_type": event_type,
                "occurred_at": now.isoformat(),
                "organization_id": str(order.organization_id),
                "aggregate": {"type": "work_order", "id": str(order.id)},
                "actor_user_id": str(actor_user_id),
                "correlation_id": str(request_id),
                "data": {
                    "number": order.number,
                    "vehicle_id": str(order.vehicle_id),
                    "status": WorkOrderStatus(order.status).value,
                },
            },
            occurred_at=now,
            attempts=0,
        )

    @staticmethod
    def _notification(
        organization_id: uuid.UUID,
        recipient_user_id: uuid.UUID,
        notification_type: str,
        title: str,
        body: str,
        order_id: uuid.UUID,
        now: datetime,
    ) -> Notification:
        return Notification(
            id=uuid.uuid4(),
            organization_id=organization_id,
            recipient_user_id=recipient_user_id,
            type=notification_type,
            title=title,
            body=body,
            entity_type="work_order",
            entity_id=order_id,
            created_at=now,
        )

    def _run_before_commit(self) -> None:
        if self._before_commit is not None:
            self._before_commit()


def order_snapshot(order: WorkOrder) -> dict[str, object]:
    return {
        "number": order.number,
        "vehicle_id": str(order.vehicle_id),
        "source_defect_id": str(order.source_defect_id) if order.source_defect_id else None,
        "maintenance_schedule_id": (
            str(order.maintenance_schedule_id) if order.maintenance_schedule_id else None
        ),
        "title": order.title,
        "priority": WorkOrderPriority(order.priority).value,
        "status": WorkOrderStatus(order.status).value,
        "assigned_mechanic_membership_id": (
            str(order.assigned_mechanic_membership_id)
            if order.assigned_mechanic_membership_id
            else None
        ),
        "labour_hours": str(order.labour_hours),
        "labour_cost": str(order.labour_cost),
        "parts_cost": str(order.parts_cost),
        "currency": order.currency,
        "version": order.version,
    }
