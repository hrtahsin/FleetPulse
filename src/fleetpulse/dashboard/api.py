from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends

from fleetpulse.auth.dependencies import require_roles
from fleetpulse.auth.roles import MembershipRole
from fleetpulse.auth.service import CurrentIdentity
from fleetpulse.dashboard.schemas import DashboardSummaryResponse
from fleetpulse.dashboard.service import DashboardService

router = APIRouter(prefix="/dashboard", tags=["dashboard"])
dashboard_reader = require_roles(MembershipRole.OWNER, MembershipRole.MANAGER)


@lru_cache
def get_dashboard_service() -> DashboardService:
    return DashboardService()


@router.get("/summary", response_model=DashboardSummaryResponse)
async def dashboard_summary(
    identity: Annotated[CurrentIdentity, Depends(dashboard_reader)],
    service: Annotated[DashboardService, Depends(get_dashboard_service)],
) -> DashboardSummaryResponse:
    return await service.summary(
        organization_id=identity.organization_id,
        currency=identity.default_currency,
    )
