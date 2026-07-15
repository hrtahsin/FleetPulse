import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import cast

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fleetpulse.notifications.exceptions import NotificationNotFoundError
from fleetpulse.notifications.models import Notification
from fleetpulse.shared.database import get_session_factory


class NotificationService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession] | None = None) -> None:
        self._session_factory = session_factory or get_session_factory()

    async def list(
        self,
        *,
        organization_id: uuid.UUID,
        recipient_user_id: uuid.UUID,
        unread_only: bool,
        limit: int,
    ) -> Sequence[Notification]:
        statement = select(Notification).where(
            Notification.organization_id == organization_id,
            Notification.recipient_user_id == recipient_user_id,
        )
        if unread_only:
            statement = statement.where(Notification.read_at.is_(None))
        statement = statement.order_by(
            Notification.created_at.desc(), Notification.id.desc()
        ).limit(limit)
        async with self._session_factory() as session:
            return (await session.scalars(statement)).all()

    async def mark_read(
        self,
        *,
        organization_id: uuid.UUID,
        recipient_user_id: uuid.UUID,
        notification_id: uuid.UUID,
    ) -> Notification:
        async with self._session_factory() as session, session.begin():
            notification = cast(
                Notification | None,
                await session.scalar(
                    select(Notification)
                    .where(
                        Notification.organization_id == organization_id,
                        Notification.recipient_user_id == recipient_user_id,
                        Notification.id == notification_id,
                    )
                    .with_for_update()
                ),
            )
            if notification is None:
                raise NotificationNotFoundError
            if notification.read_at is None:
                notification.read_at = datetime.now(UTC)
            return notification

    async def unread_count(
        self, *, organization_id: uuid.UUID, recipient_user_id: uuid.UUID
    ) -> int:
        async with self._session_factory() as session:
            return int(
                await session.scalar(
                    select(func.count(Notification.id)).where(
                        Notification.organization_id == organization_id,
                        Notification.recipient_user_id == recipient_user_id,
                        Notification.read_at.is_(None),
                    )
                )
                or 0
            )

    async def mark_all_read(
        self, *, organization_id: uuid.UUID, recipient_user_id: uuid.UUID
    ) -> int:
        async with self._session_factory() as session, session.begin():
            unread = int(
                await session.scalar(
                    select(func.count(Notification.id)).where(
                        Notification.organization_id == organization_id,
                        Notification.recipient_user_id == recipient_user_id,
                        Notification.read_at.is_(None),
                    )
                )
                or 0
            )
            await session.execute(
                update(Notification)
                .where(
                    Notification.organization_id == organization_id,
                    Notification.recipient_user_id == recipient_user_id,
                    Notification.read_at.is_(None),
                )
                .values(read_at=datetime.now(UTC))
            )
            return unread
