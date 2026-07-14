import base64
import binascii
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fleetpulse.shared.database import get_session_factory
from fleetpulse.vehicles.exceptions import (
    DuplicateVehicleError,
    InvalidStatusTransitionError,
    InvalidVehicleCursorError,
    OdometerRollbackError,
    StaleVehicleVersionError,
    StatusReasonRequiredError,
    VehicleNotFoundError,
)
from fleetpulse.vehicles.models import Vehicle, VehicleStatusHistory
from fleetpulse.vehicles.repository import VehicleRepository
from fleetpulse.vehicles.status import VehicleStatus

LEGAL_STATUS_TRANSITIONS: Mapping[VehicleStatus, frozenset[VehicleStatus]] = {
    VehicleStatus.AVAILABLE: frozenset(
        {
            VehicleStatus.IN_SERVICE,
            VehicleStatus.MAINTENANCE_DUE,
            VehicleStatus.OUT_OF_SERVICE,
            VehicleStatus.RETIRED,
        }
    ),
    VehicleStatus.IN_SERVICE: frozenset(
        {
            VehicleStatus.AVAILABLE,
            VehicleStatus.MAINTENANCE_DUE,
            VehicleStatus.OUT_OF_SERVICE,
        }
    ),
    VehicleStatus.MAINTENANCE_DUE: frozenset(
        {
            VehicleStatus.AVAILABLE,
            VehicleStatus.IN_SERVICE,
            VehicleStatus.UNDER_REPAIR,
            VehicleStatus.OUT_OF_SERVICE,
            VehicleStatus.RETIRED,
        }
    ),
    VehicleStatus.UNDER_REPAIR: frozenset(
        {
            VehicleStatus.AVAILABLE,
            VehicleStatus.IN_SERVICE,
            VehicleStatus.OUT_OF_SERVICE,
            VehicleStatus.RETIRED,
        }
    ),
    VehicleStatus.OUT_OF_SERVICE: frozenset(
        {
            VehicleStatus.AVAILABLE,
            VehicleStatus.UNDER_REPAIR,
            VehicleStatus.RETIRED,
        }
    ),
    VehicleStatus.RETIRED: frozenset(),
}

EDITABLE_FIELDS = frozenset(
    {"unit_number", "vin", "registration", "make", "model", "model_year", "fuel_type"}
)


@dataclass(frozen=True, slots=True)
class CreateVehicle:
    unit_number: str
    vin: str | None
    registration: str | None
    make: str
    model: str
    model_year: int
    fuel_type: str | None
    odometer_km: Decimal
    status: VehicleStatus = VehicleStatus.AVAILABLE


@dataclass(frozen=True, slots=True)
class VehiclePage:
    items: Sequence[Vehicle]
    next_cursor: str | None


class VehicleService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._session_factory = session_factory or get_session_factory()
        self._clock = clock or (lambda: datetime.now(UTC))

    async def list(
        self,
        *,
        organization_id: uuid.UUID,
        limit: int,
        cursor: str | None,
        status: VehicleStatus | None,
        query: str | None,
    ) -> VehiclePage:
        after_id = decode_cursor(cursor) if cursor else None
        async with self._session_factory() as session:
            records = await VehicleRepository(session).list(
                organization_id=organization_id,
                limit=limit + 1,
                after_id=after_id,
                status=status,
                query=query,
            )
        has_next = len(records) > limit
        items = records[:limit]
        next_cursor = encode_cursor(items[-1].id) if has_next and items else None
        return VehiclePage(items=items, next_cursor=next_cursor)

    async def get(self, *, organization_id: uuid.UUID, vehicle_id: uuid.UUID) -> Vehicle:
        async with self._session_factory() as session:
            vehicle = await VehicleRepository(session).get(organization_id, vehicle_id)
        if vehicle is None:
            raise VehicleNotFoundError
        return vehicle

    async def create(
        self,
        *,
        organization_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        data: CreateVehicle,
    ) -> Vehicle:
        now = self._clock()
        try:
            async with self._session_factory() as session, session.begin():
                repository = VehicleRepository(session)
                if await repository.has_identity_conflict(
                    organization_id=organization_id,
                    unit_number=data.unit_number,
                    vin=data.vin,
                ):
                    raise DuplicateVehicleError
                vehicle = Vehicle(
                    id=uuid.uuid4(),
                    organization_id=organization_id,
                    unit_number=data.unit_number,
                    vin=data.vin,
                    registration=data.registration,
                    make=data.make,
                    model=data.model,
                    model_year=data.model_year,
                    fuel_type=data.fuel_type,
                    odometer_km=data.odometer_km,
                    status=data.status,
                    version=1,
                    retired_at=now if data.status is VehicleStatus.RETIRED else None,
                )
                repository.add(vehicle)
                repository.add(
                    VehicleStatusHistory(
                        id=uuid.uuid4(),
                        organization_id=organization_id,
                        vehicle_id=vehicle.id,
                        from_status=None,
                        to_status=data.status,
                        reason_code="vehicle_created",
                        changed_by_user_id=actor_user_id,
                        created_at=now,
                    )
                )
            return vehicle
        except IntegrityError as exc:
            raise DuplicateVehicleError from exc

    async def update(
        self,
        *,
        organization_id: uuid.UUID,
        vehicle_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        expected_version: int,
        changes: Mapping[str, Any],
        status_reason: str | None,
    ) -> Vehicle:
        now = self._clock()
        try:
            async with self._session_factory() as session, session.begin():
                repository = VehicleRepository(session)
                vehicle = await repository.get(organization_id, vehicle_id, for_update=True)
                if vehicle is None:
                    raise VehicleNotFoundError
                if vehicle.version != expected_version:
                    raise StaleVehicleVersionError

                next_status = changes.get("status", vehicle.status)
                if not isinstance(next_status, VehicleStatus):
                    next_status = VehicleStatus(next_status)
                status_changed = next_status != vehicle.status
                normalized_status_reason = status_reason.strip() if status_reason else None
                if status_changed:
                    if next_status not in LEGAL_STATUS_TRANSITIONS[VehicleStatus(vehicle.status)]:
                        raise InvalidStatusTransitionError
                    if not normalized_status_reason:
                        raise StatusReasonRequiredError

                next_odometer = changes.get("odometer_km", vehicle.odometer_km)
                if not isinstance(next_odometer, Decimal):
                    next_odometer = Decimal(str(next_odometer))
                if next_odometer < vehicle.odometer_km:
                    raise OdometerRollbackError

                next_unit_number = str(changes.get("unit_number", vehicle.unit_number))
                next_vin_value = changes.get("vin", vehicle.vin)
                next_vin = str(next_vin_value) if next_vin_value is not None else None
                if await repository.has_identity_conflict(
                    organization_id=organization_id,
                    unit_number=next_unit_number,
                    vin=next_vin,
                    exclude_vehicle_id=vehicle.id,
                ):
                    raise DuplicateVehicleError

                for field in EDITABLE_FIELDS & changes.keys():
                    setattr(vehicle, field, changes[field])
                vehicle.odometer_km = next_odometer
                if status_changed:
                    previous_status = VehicleStatus(vehicle.status)
                    vehicle.status = next_status
                    vehicle.retired_at = now if next_status is VehicleStatus.RETIRED else None
                    repository.add(
                        VehicleStatusHistory(
                            id=uuid.uuid4(),
                            organization_id=organization_id,
                            vehicle_id=vehicle.id,
                            from_status=previous_status,
                            to_status=next_status,
                            reason_code=normalized_status_reason,
                            changed_by_user_id=actor_user_id,
                            created_at=now,
                        )
                    )
                vehicle.version += 1
            return vehicle
        except IntegrityError as exc:
            raise DuplicateVehicleError from exc

    async def history(
        self, *, organization_id: uuid.UUID, vehicle_id: uuid.UUID, limit: int
    ) -> Sequence[VehicleStatusHistory]:
        async with self._session_factory() as session:
            repository = VehicleRepository(session)
            if await repository.get(organization_id, vehicle_id) is None:
                raise VehicleNotFoundError
            return await repository.list_history(
                organization_id=organization_id, vehicle_id=vehicle_id, limit=limit
            )


def encode_cursor(vehicle_id: uuid.UUID) -> str:
    return base64.urlsafe_b64encode(vehicle_id.bytes).rstrip(b"=").decode("ascii")


def decode_cursor(cursor: str) -> uuid.UUID:
    try:
        padding = "=" * (-len(cursor) % 4)
        raw = base64.b64decode(cursor + padding, altchars=b"-_", validate=True)
        if len(raw) != 16:
            raise ValueError
        return uuid.UUID(bytes=raw)
    except (binascii.Error, ValueError) as exc:
        raise InvalidVehicleCursorError from exc
