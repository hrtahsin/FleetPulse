import hashlib
import json
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fleetpulse.audit.models import AuditEvent
from fleetpulse.defects.models import Defect
from fleetpulse.defects.types import DefectSeverity, DefectStatus
from fleetpulse.inspections.exceptions import (
    IdempotencyPayloadMismatchError,
    InspectionNotFoundError,
    InspectionOdometerRollbackError,
    InspectionTemplateNotFoundError,
    InspectionVehicleNotFoundError,
    InvalidInspectionResponseError,
    MissingInspectionResponseError,
    VehicleNotInspectableError,
)
from fleetpulse.inspections.models import (
    Inspection,
    InspectionResponse,
    InspectionTemplate,
    InspectionTemplateItem,
)
from fleetpulse.inspections.repository import InspectionRepository
from fleetpulse.inspections.types import InspectionStatus, ResponseType
from fleetpulse.notifications.models import Notification
from fleetpulse.outbox.models import OutboxEvent
from fleetpulse.shared.database import get_session_factory
from fleetpulse.vehicles.models import VehicleStatusHistory
from fleetpulse.vehicles.status import VehicleStatus

INSPECTABLE_STATUSES = frozenset(
    {VehicleStatus.AVAILABLE, VehicleStatus.IN_SERVICE, VehicleStatus.MAINTENANCE_DUE}
)


@dataclass(frozen=True, slots=True)
class ReportedDefect:
    category: str
    description: str
    severity: DefectSeverity


@dataclass(frozen=True, slots=True)
class SubmittedResponse:
    template_item_id: uuid.UUID
    result: str
    comment: str | None = None
    defect: ReportedDefect | None = None


@dataclass(frozen=True, slots=True)
class SubmitInspection:
    vehicle_id: uuid.UUID
    template_id: uuid.UUID
    odometer_km: Decimal
    notes: str | None
    responses: Sequence[SubmittedResponse]


@dataclass(frozen=True, slots=True)
class InspectionDetails:
    inspection: Inspection
    responses: Sequence[InspectionResponse]
    defects: Sequence[Defect]
    replayed: bool = False


@dataclass(frozen=True, slots=True)
class ActiveTemplate:
    template: InspectionTemplate
    items: Sequence[InspectionTemplateItem]


class InspectionService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
        clock: Callable[[], datetime] | None = None,
        before_commit: Callable[[], None] | None = None,
    ) -> None:
        self._session_factory = session_factory or get_session_factory()
        self._clock = clock or (lambda: datetime.now(UTC))
        self._before_commit = before_commit

    async def active_template(self, organization_id: uuid.UUID) -> ActiveTemplate:
        async with self._session_factory() as session:
            result = await InspectionRepository(session).get_active_template(organization_id)
        if result is None:
            raise InspectionTemplateNotFoundError
        return ActiveTemplate(template=result[0], items=result[1])

    async def submit(
        self,
        *,
        organization_id: uuid.UUID,
        driver_membership_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        idempotency_key: str,
        request_id: uuid.UUID,
        submission: SubmitInspection,
    ) -> InspectionDetails:
        payload_hash = hash_submission(submission)
        try:
            async with self._session_factory() as session, session.begin():
                repository = InspectionRepository(session)
                existing = await repository.get_by_idempotency_key(organization_id, idempotency_key)
                if existing is not None:
                    return await self._replayed(repository, existing, payload_hash)
                details = await self._create_submission(
                    repository=repository,
                    organization_id=organization_id,
                    driver_membership_id=driver_membership_id,
                    actor_user_id=actor_user_id,
                    idempotency_key=idempotency_key,
                    request_id=request_id,
                    payload_hash=payload_hash,
                    submission=submission,
                )
                if self._before_commit is not None:
                    self._before_commit()
                return details
        except IntegrityError:
            return await self._load_concurrent_replay(
                organization_id=organization_id,
                idempotency_key=idempotency_key,
                payload_hash=payload_hash,
            )

    async def get(
        self, *, organization_id: uuid.UUID, inspection_id: uuid.UUID
    ) -> InspectionDetails:
        async with self._session_factory() as session:
            repository = InspectionRepository(session)
            inspection = await repository.get_inspection(organization_id, inspection_id)
            if inspection is None:
                raise InspectionNotFoundError
            return InspectionDetails(
                inspection=inspection,
                responses=await repository.list_responses(inspection.id),
                defects=await repository.list_defects(inspection.id),
            )

    async def list(
        self,
        *,
        organization_id: uuid.UUID,
        driver_membership_id: uuid.UUID | None,
        limit: int,
    ) -> Sequence[Inspection]:
        async with self._session_factory() as session:
            return await InspectionRepository(session).list_inspections(
                organization_id=organization_id,
                driver_membership_id=driver_membership_id,
                limit=limit,
            )

    async def _create_submission(
        self,
        *,
        repository: InspectionRepository,
        organization_id: uuid.UUID,
        driver_membership_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        idempotency_key: str,
        request_id: uuid.UUID,
        payload_hash: str,
        submission: SubmitInspection,
    ) -> InspectionDetails:
        template_result = await repository.get_template(organization_id, submission.template_id)
        if template_result is None:
            raise InspectionTemplateNotFoundError
        _, template_items = template_result
        validated = validate_responses(template_items, submission.responses)

        vehicle = await repository.get_vehicle_for_update(organization_id, submission.vehicle_id)
        if vehicle is None:
            raise InspectionVehicleNotFoundError
        current_status = VehicleStatus(vehicle.status)
        if current_status not in INSPECTABLE_STATUSES:
            raise VehicleNotInspectableError
        if submission.odometer_km < vehicle.odometer_km:
            raise InspectionOdometerRollbackError

        now = self._clock()
        inspection = Inspection(
            id=uuid.uuid4(),
            organization_id=organization_id,
            vehicle_id=vehicle.id,
            driver_membership_id=driver_membership_id,
            template_id=submission.template_id,
            odometer_km=submission.odometer_km,
            status=InspectionStatus.SUBMITTED,
            notes=submission.notes,
            submitted_at=now,
            idempotency_key=idempotency_key,
            request_hash=payload_hash,
            created_at=now,
        )
        responses: list[InspectionResponse] = []
        defects: list[Defect] = []
        for response_input in validated:
            response = InspectionResponse(
                id=uuid.uuid4(),
                inspection_id=inspection.id,
                template_item_id=response_input.template_item_id,
                result=response_input.result,
                comment=response_input.comment,
            )
            responses.append(response)
            if response_input.defect is not None:
                defects.append(
                    Defect(
                        id=uuid.uuid4(),
                        organization_id=organization_id,
                        inspection_id=inspection.id,
                        inspection_response_id=response.id,
                        vehicle_id=vehicle.id,
                        category=response_input.defect.category,
                        description=response_input.defect.description,
                        severity=response_input.defect.severity,
                        status=DefectStatus.OPEN,
                        reported_by_user_id=actor_user_id,
                        created_at=now,
                        updated_at=now,
                    )
                )

        vehicle.odometer_km = submission.odometer_km
        vehicle.version += 1
        repository.add(inspection, *responses, *defects)
        critical_defects = [
            defect for defect in defects if defect.severity == DefectSeverity.CRITICAL
        ]
        if critical_defects:
            vehicle.status = VehicleStatus.OUT_OF_SERVICE
            repository.add(
                VehicleStatusHistory(
                    id=uuid.uuid4(),
                    organization_id=organization_id,
                    vehicle_id=vehicle.id,
                    from_status=current_status,
                    to_status=VehicleStatus.OUT_OF_SERVICE,
                    reason_code="critical_defect",
                    reason_reference_id=critical_defects[0].id,
                    changed_by_user_id=actor_user_id,
                    created_at=now,
                )
            )

        repository.add(
            self._audit(
                organization_id=organization_id,
                actor_user_id=actor_user_id,
                action="inspection.submitted",
                entity_type="inspection",
                entity_id=inspection.id,
                request_id=request_id,
                after_data={
                    "vehicle_id": str(vehicle.id),
                    "status": InspectionStatus.SUBMITTED.value,
                    "defect_count": len(defects),
                },
                now=now,
            ),
            self._event(
                event_type="inspection.submitted.v1",
                organization_id=organization_id,
                aggregate_type="inspection",
                aggregate_id=inspection.id,
                actor_user_id=actor_user_id,
                correlation_id=request_id,
                data={"vehicle_id": str(vehicle.id), "defect_count": len(defects)},
                now=now,
            ),
        )
        for defect in defects:
            await self._record_defect_side_effects(
                repository=repository,
                defect=defect,
                organization_id=organization_id,
                actor_user_id=actor_user_id,
                request_id=request_id,
                now=now,
            )
        if critical_defects:
            repository.add(
                self._audit(
                    organization_id=organization_id,
                    actor_user_id=actor_user_id,
                    action="vehicle.status_changed",
                    entity_type="vehicle",
                    entity_id=vehicle.id,
                    request_id=request_id,
                    before_data={"status": current_status.value},
                    after_data={"status": VehicleStatus.OUT_OF_SERVICE.value},
                    now=now,
                ),
                self._event(
                    event_type="vehicle.status_changed.v1",
                    organization_id=organization_id,
                    aggregate_type="vehicle",
                    aggregate_id=vehicle.id,
                    actor_user_id=actor_user_id,
                    correlation_id=request_id,
                    data={
                        "from_status": current_status.value,
                        "to_status": VehicleStatus.OUT_OF_SERVICE.value,
                        "reason": "critical_defect",
                    },
                    now=now,
                ),
            )
        return InspectionDetails(inspection=inspection, responses=responses, defects=defects)

    async def _record_defect_side_effects(
        self,
        *,
        repository: InspectionRepository,
        defect: Defect,
        organization_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        request_id: uuid.UUID,
        now: datetime,
    ) -> None:
        severity = DefectSeverity(defect.severity)
        event_type = (
            "defect.critical_reported.v1"
            if severity is DefectSeverity.CRITICAL
            else "defect.reported.v1"
        )
        repository.add(
            self._audit(
                organization_id=organization_id,
                actor_user_id=actor_user_id,
                action="defect.reported",
                entity_type="defect",
                entity_id=defect.id,
                request_id=request_id,
                after_data={
                    "vehicle_id": str(defect.vehicle_id),
                    "severity": severity.value,
                    "status": DefectStatus.OPEN.value,
                },
                now=now,
            ),
            self._event(
                event_type=event_type,
                organization_id=organization_id,
                aggregate_type="defect",
                aggregate_id=defect.id,
                actor_user_id=actor_user_id,
                correlation_id=request_id,
                data={
                    "vehicle_id": str(defect.vehicle_id),
                    "inspection_id": str(defect.inspection_id),
                    "severity": severity.value,
                },
                now=now,
            ),
        )
        for recipient_user_id in await repository.management_user_ids(organization_id):
            repository.add(
                Notification(
                    id=uuid.uuid4(),
                    organization_id=organization_id,
                    recipient_user_id=recipient_user_id,
                    type=(
                        "critical_defect_reported"
                        if severity is DefectSeverity.CRITICAL
                        else "defect_reported"
                    ),
                    title=f"{severity.value.title()} vehicle defect reported",
                    body=defect.description,
                    entity_type="defect",
                    entity_id=defect.id,
                    created_at=now,
                )
            )

    async def _replayed(
        self,
        repository: InspectionRepository,
        inspection: Inspection,
        payload_hash: str,
    ) -> InspectionDetails:
        if inspection.request_hash != payload_hash:
            raise IdempotencyPayloadMismatchError
        return InspectionDetails(
            inspection=inspection,
            responses=await repository.list_responses(inspection.id),
            defects=await repository.list_defects(inspection.id),
            replayed=True,
        )

    async def _load_concurrent_replay(
        self, *, organization_id: uuid.UUID, idempotency_key: str, payload_hash: str
    ) -> InspectionDetails:
        async with self._session_factory() as session:
            repository = InspectionRepository(session)
            inspection = await repository.get_by_idempotency_key(organization_id, idempotency_key)
            if inspection is None:
                raise InvalidInspectionResponseError from None
            return await self._replayed(repository, inspection, payload_hash)

    @staticmethod
    def _audit(
        *,
        organization_id: uuid.UUID,
        actor_user_id: uuid.UUID,
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
        actor_user_id: uuid.UUID,
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
                "actor_user_id": str(actor_user_id),
                "correlation_id": str(correlation_id),
                "data": dict(data),
            },
            occurred_at=now,
            attempts=0,
        )


def validate_responses(
    template_items: Sequence[InspectionTemplateItem],
    responses: Sequence[SubmittedResponse],
) -> Sequence[SubmittedResponse]:
    items_by_id = {item.id: item for item in template_items}
    response_ids = [response.template_item_id for response in responses]
    if len(response_ids) != len(set(response_ids)):
        raise InvalidInspectionResponseError
    if not set(response_ids) <= items_by_id.keys():
        raise InvalidInspectionResponseError
    required_ids = {item.id for item in template_items if item.required}
    if not required_ids <= set(response_ids):
        raise MissingInspectionResponseError

    for response in responses:
        item = items_by_id[response.template_item_id]
        normalized = response.result.strip().lower()
        response_type = ResponseType(item.response_type)
        if response_type is ResponseType.PASS_FAIL:
            if normalized not in {"pass", "fail"}:
                raise InvalidInspectionResponseError
            if normalized == "fail" and response.defect is None:
                raise InvalidInspectionResponseError
            if normalized == "pass" and response.defect is not None:
                raise InvalidInspectionResponseError
        elif response_type is ResponseType.BOOLEAN and normalized not in {"true", "false"}:
            raise InvalidInspectionResponseError
        elif response_type is ResponseType.NUMBER:
            try:
                Decimal(normalized)
            except InvalidOperation as exc:
                raise InvalidInspectionResponseError from exc
        elif response_type is ResponseType.TEXT and not response.result.strip():
            raise InvalidInspectionResponseError
    return responses


def hash_submission(submission: SubmitInspection) -> str:
    normalized_responses = sorted(
        (
            {
                "template_item_id": str(response.template_item_id),
                "result": response.result,
                "comment": response.comment,
                "defect": (
                    {
                        "category": response.defect.category,
                        "description": response.defect.description,
                        "severity": response.defect.severity.value,
                    }
                    if response.defect
                    else None
                ),
            }
            for response in submission.responses
        ),
        key=lambda response: str(response["template_item_id"]),
    )
    payload = {
        "vehicle_id": str(submission.vehicle_id),
        "template_id": str(submission.template_id),
        "odometer_km": str(submission.odometer_km),
        "notes": submission.notes,
        "responses": normalized_responses,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()
