import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fleetpulse.audit.models import AuditEvent
from fleetpulse.auth.models import User
from fleetpulse.shared.database import get_session_factory


@dataclass(frozen=True, slots=True)
class AuditRecord:
    event: AuditEvent
    actor: User | None


class AuditService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
    ) -> None:
        self._session_factory = session_factory or get_session_factory()

    async def list(
        self,
        *,
        organization_id: uuid.UUID,
        entity_type: str | None,
        entity_id: uuid.UUID | None,
        action: str | None,
        actor_user_id: uuid.UUID | None,
        limit: int,
    ) -> list[AuditRecord]:
        statement = (
            select(AuditEvent, User)
            .outerjoin(User, User.id == AuditEvent.actor_user_id)
            .where(AuditEvent.organization_id == organization_id)
        )
        if entity_type is not None:
            statement = statement.where(AuditEvent.entity_type == entity_type)
        if entity_id is not None:
            statement = statement.where(AuditEvent.entity_id == entity_id)
        if action is not None:
            statement = statement.where(AuditEvent.action == action)
        if actor_user_id is not None:
            statement = statement.where(AuditEvent.actor_user_id == actor_user_id)
        statement = statement.order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc()).limit(
            limit
        )
        async with self._session_factory() as session:
            rows = (await session.execute(statement)).all()
        return [AuditRecord(event=row[0], actor=row[1]) for row in rows]
