from collections.abc import Sequence
from typing import cast
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from fleetpulse.auth.models import OrganizationMembership, User
from fleetpulse.auth.roles import MANAGEMENT_ROLES
from fleetpulse.defects.models import Defect
from fleetpulse.inspections.models import (
    Inspection,
    InspectionResponse,
    InspectionTemplate,
    InspectionTemplateItem,
)
from fleetpulse.vehicles.models import Vehicle


class InspectionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_active_template(
        self, organization_id: UUID
    ) -> tuple[InspectionTemplate, Sequence[InspectionTemplateItem]] | None:
        template = await self._session.scalar(
            select(InspectionTemplate)
            .where(
                InspectionTemplate.organization_id == organization_id,
                InspectionTemplate.is_active.is_(True),
            )
            .order_by(InspectionTemplate.updated_at.desc())
            .limit(1)
        )
        if template is None:
            return None
        return template, await self.get_template_items(template.id)

    async def get_template(
        self, organization_id: UUID, template_id: UUID
    ) -> tuple[InspectionTemplate, Sequence[InspectionTemplateItem]] | None:
        template = await self._session.scalar(
            select(InspectionTemplate).where(
                InspectionTemplate.organization_id == organization_id,
                InspectionTemplate.id == template_id,
                InspectionTemplate.is_active.is_(True),
            )
        )
        if template is None:
            return None
        return template, await self.get_template_items(template.id)

    async def get_template_items(self, template_id: UUID) -> Sequence[InspectionTemplateItem]:
        statement = (
            select(InspectionTemplateItem)
            .where(InspectionTemplateItem.template_id == template_id)
            .order_by(InspectionTemplateItem.sort_order, InspectionTemplateItem.id)
        )
        return (await self._session.scalars(statement)).all()

    async def get_vehicle_for_update(
        self, organization_id: UUID, vehicle_id: UUID
    ) -> Vehicle | None:
        statement = (
            select(Vehicle)
            .where(Vehicle.organization_id == organization_id, Vehicle.id == vehicle_id)
            .with_for_update()
        )
        return cast(Vehicle | None, await self._session.scalar(statement))

    async def get_by_idempotency_key(
        self, organization_id: UUID, idempotency_key: str
    ) -> Inspection | None:
        return cast(
            Inspection | None,
            await self._session.scalar(
                select(Inspection).where(
                    Inspection.organization_id == organization_id,
                    Inspection.idempotency_key == idempotency_key,
                )
            ),
        )

    async def get_inspection(self, organization_id: UUID, inspection_id: UUID) -> Inspection | None:
        return cast(
            Inspection | None,
            await self._session.scalar(
                select(Inspection).where(
                    Inspection.organization_id == organization_id,
                    Inspection.id == inspection_id,
                )
            ),
        )

    async def list_inspections(
        self,
        *,
        organization_id: UUID,
        driver_membership_id: UUID | None,
        limit: int,
    ) -> Sequence[Inspection]:
        statement: Select[tuple[Inspection]] = select(Inspection).where(
            Inspection.organization_id == organization_id
        )
        if driver_membership_id is not None:
            statement = statement.where(Inspection.driver_membership_id == driver_membership_id)
        statement = statement.order_by(Inspection.submitted_at.desc(), Inspection.id.desc()).limit(
            limit
        )
        return (await self._session.scalars(statement)).all()

    async def list_responses(self, inspection_id: UUID) -> Sequence[InspectionResponse]:
        return (
            await self._session.scalars(
                select(InspectionResponse)
                .where(InspectionResponse.inspection_id == inspection_id)
                .order_by(InspectionResponse.id)
            )
        ).all()

    async def list_defects(self, inspection_id: UUID) -> Sequence[Defect]:
        return (
            await self._session.scalars(
                select(Defect)
                .where(Defect.inspection_id == inspection_id)
                .order_by(Defect.created_at, Defect.id)
            )
        ).all()

    async def management_user_ids(self, organization_id: UUID) -> Sequence[UUID]:
        statement = (
            select(User.id)
            .join(OrganizationMembership, OrganizationMembership.user_id == User.id)
            .where(
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.role.in_([role.value for role in MANAGEMENT_ROLES]),
                User.is_active.is_(True),
            )
            .order_by(User.id)
        )
        return (await self._session.scalars(statement)).all()

    def add(self, *records: object) -> None:
        self._session.add_all(records)

    async def flush(self) -> None:
        await self._session.flush()
