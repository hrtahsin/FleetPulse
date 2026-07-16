import uuid
from datetime import UTC, datetime
from decimal import Decimal

from fastapi.testclient import TestClient

from apps.api.main import app
from fleetpulse.audit.api import get_audit_service
from fleetpulse.audit.models import AuditEvent
from fleetpulse.audit.service import AuditRecord
from fleetpulse.auth.dependencies import get_auth_service
from fleetpulse.auth.models import User
from fleetpulse.auth.roles import MembershipRole
from fleetpulse.auth.service import CurrentIdentity
from fleetpulse.dashboard.api import get_dashboard_service
from fleetpulse.dashboard.schemas import (
    DashboardSummaryResponse,
    DefectSummary,
    MaintenanceSummary,
    VehicleSummary,
    WorkOrderSummary,
)

ORGANIZATION_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
USER_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
EVENT_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")
ENTITY_ID = uuid.UUID("44444444-4444-4444-4444-444444444444")


class FakeAuthService:
    def __init__(self, role: MembershipRole) -> None:
        self.role = role

    async def current_identity(self, _: str) -> CurrentIdentity:
        return CurrentIdentity(
            user_id=USER_ID,
            email="manager@example.com",
            display_name="Demo Manager",
            membership_id=uuid.uuid4(),
            organization_id=ORGANIZATION_ID,
            organization_name="Demo Fleet",
            organization_slug="demo-fleet",
            organization_timezone="America/St_Johns",
            default_currency="CAD",
            role=self.role,
        )


class FakeDashboardService:
    def __init__(self) -> None:
        self.organization_id: uuid.UUID | None = None

    async def summary(
        self, *, organization_id: uuid.UUID, currency: str
    ) -> DashboardSummaryResponse:
        self.organization_id = organization_id
        return DashboardSummaryResponse(
            generated_at=datetime(2026, 7, 15, tzinfo=UTC),
            currency=currency,
            vehicles=VehicleSummary(
                total=4,
                operational=2,
                unavailable=2,
                available=1,
                in_service=1,
                maintenance_due=0,
                under_repair=1,
                out_of_service=1,
                retired=0,
            ),
            defects=DefectSummary(active=2, critical=1, triaged=1, in_repair=0),
            maintenance=MaintenanceSummary(upcoming=1, due=1, overdue=0),
            work_orders=WorkOrderSummary(
                active=1,
                unassigned=0,
                waiting_parts=0,
                awaiting_verification=1,
                repair_cost_30_days=Decimal("527.49"),
            ),
        )


class FakeAuditService:
    def __init__(self) -> None:
        self.filters: dict[str, object] = {}

    async def list(self, **filters: object) -> list[AuditRecord]:
        self.filters = filters
        return [
            AuditRecord(
                event=AuditEvent(
                    id=EVENT_ID,
                    organization_id=ORGANIZATION_ID,
                    actor_user_id=USER_ID,
                    action="work_order.status_changed",
                    entity_type="work_order",
                    entity_id=ENTITY_ID,
                    before_data={"status": "completed"},
                    after_data={"status": "verified"},
                    request_id=uuid.uuid4(),
                    created_at=datetime(2026, 7, 15, tzinfo=UTC),
                ),
                actor=User(
                    id=USER_ID,
                    email="manager@example.com",
                    display_name="Demo Manager",
                    password_hash="unused",
                    is_active=True,
                ),
            )
        ]


def test_manager_reads_tenant_dashboard_summary() -> None:
    dashboard = FakeDashboardService()
    app.dependency_overrides[get_auth_service] = lambda: FakeAuthService(MembershipRole.MANAGER)
    app.dependency_overrides[get_dashboard_service] = lambda: dashboard
    with TestClient(app) as client:
        response = client.get(
            "/api/v1/dashboard/summary",
            headers={"Authorization": "Bearer valid"},
        )
    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["vehicles"]["unavailable"] == 2
    assert response.json()["work_orders"]["repair_cost_30_days"] == "527.49"
    assert dashboard.organization_id == ORGANIZATION_ID


def test_audit_filters_are_tenant_scoped_and_actor_is_expanded() -> None:
    audit = FakeAuditService()
    app.dependency_overrides[get_auth_service] = lambda: FakeAuthService(MembershipRole.OWNER)
    app.dependency_overrides[get_audit_service] = lambda: audit
    with TestClient(app) as client:
        response = client.get(
            f"/api/v1/audit-events?entity_type=work_order&entity_id={ENTITY_ID}&limit=10",
            headers={"Authorization": "Bearer valid"},
        )
    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["items"][0]["actor"]["display_name"] == "Demo Manager"
    assert audit.filters["organization_id"] == ORGANIZATION_ID
    assert audit.filters["entity_id"] == ENTITY_ID
    assert audit.filters["limit"] == 10


def test_mechanic_cannot_read_management_reporting() -> None:
    app.dependency_overrides[get_auth_service] = lambda: FakeAuthService(MembershipRole.MECHANIC)
    with TestClient(app) as client:
        dashboard = client.get(
            "/api/v1/dashboard/summary",
            headers={"Authorization": "Bearer valid"},
        )
        audit = client.get(
            "/api/v1/audit-events",
            headers={"Authorization": "Bearer valid"},
        )
    app.dependency_overrides.clear()

    assert dashboard.status_code == 403
    assert audit.status_code == 403
