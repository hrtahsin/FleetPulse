import uuid
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal

from fastapi.testclient import TestClient

from apps.api.main import app
from fleetpulse.auth.dependencies import get_auth_service
from fleetpulse.auth.roles import MembershipRole
from fleetpulse.auth.service import CurrentIdentity
from fleetpulse.work_orders.api import get_work_order_service
from fleetpulse.work_orders.exceptions import WorkOrderStaleVersionError
from fleetpulse.work_orders.models import WorkOrder, WorkOrderCostItem, WorkOrderNote
from fleetpulse.work_orders.service import AddCostItem, CreateWorkOrder, WorkOrderDetails
from fleetpulse.work_orders.types import WorkOrderStatus

ORGANIZATION_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")
USER_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
MEMBERSHIP_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
VEHICLE_ID = uuid.UUID("44444444-4444-4444-4444-444444444444")
DEFECT_ID = uuid.UUID("55555555-5555-5555-5555-555555555555")
ORDER_ID = uuid.UUID("66666666-6666-6666-6666-666666666666")
NOW = datetime(2026, 7, 14, 12, 0, tzinfo=UTC)


class FakeAuthService:
    def __init__(self, role: MembershipRole) -> None:
        self.role = role

    async def current_identity(self, _: str) -> CurrentIdentity:
        return CurrentIdentity(
            user_id=USER_ID,
            email=f"{self.role.value}@example.com",
            display_name="Fleet User",
            membership_id=MEMBERSHIP_ID,
            organization_id=ORGANIZATION_ID,
            organization_name="Demo Fleet",
            organization_slug="demo-fleet",
            organization_timezone="America/St_Johns",
            default_currency="CAD",
            role=self.role,
        )


class FakeWorkOrderService:
    def __init__(self) -> None:
        self.last_organization_id: uuid.UUID | None = None
        self.last_create: CreateWorkOrder | None = None
        self.last_transition_role: MembershipRole | None = None

    async def list(
        self,
        *,
        organization_id: uuid.UUID,
        actor_role: MembershipRole,
        actor_membership_id: uuid.UUID,
        status: WorkOrderStatus | None,
        limit: int,
    ) -> Sequence[WorkOrder]:
        self.last_organization_id = organization_id
        return [_order()]

    async def get(
        self,
        *,
        organization_id: uuid.UUID,
        work_order_id: uuid.UUID,
        actor_role: MembershipRole,
        actor_membership_id: uuid.UUID,
    ) -> WorkOrderDetails:
        self.last_organization_id = organization_id
        return WorkOrderDetails(order=_order(), notes=[], cost_items=[])

    async def create(
        self,
        *,
        organization_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        request_id: uuid.UUID,
        data: CreateWorkOrder,
    ) -> WorkOrder:
        self.last_organization_id = organization_id
        self.last_create = data
        return _order()

    async def update(
        self,
        *,
        organization_id: uuid.UUID,
        work_order_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        request_id: uuid.UUID,
        expected_version: int,
        changes: Mapping[str, object],
    ) -> WorkOrder:
        self.last_organization_id = organization_id
        return _order(version=expected_version + 1)

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
        self.last_organization_id = organization_id
        self.last_transition_role = actor_role
        if expected_version == 99:
            raise WorkOrderStaleVersionError
        return _order(status=next_status, version=expected_version + 1)

    async def add_note(self, **_: object) -> WorkOrderNote:
        return WorkOrderNote(
            id=uuid.uuid4(),
            organization_id=ORGANIZATION_ID,
            work_order_id=ORDER_ID,
            author_user_id=USER_ID,
            body="Diagnosis",
            created_at=NOW,
        )

    async def add_cost_item(
        self, *, data: AddCostItem, **_: object
    ) -> tuple[WorkOrderCostItem, WorkOrder]:
        return (
            WorkOrderCostItem(
                id=uuid.uuid4(),
                organization_id=ORGANIZATION_ID,
                work_order_id=ORDER_ID,
                kind=data.kind,
                description=data.description,
                quantity=data.quantity,
                unit_cost=data.unit_cost,
                created_at=NOW,
            ),
            _order(version=2),
        )


def test_manager_creates_defect_work_order_with_server_tenant_and_currency() -> None:
    client, service = _client(MembershipRole.MANAGER)
    with client:
        response = client.post(
            f"/api/v1/defects/{DEFECT_ID}/work-order",
            headers={"Authorization": "Bearer valid"},
            json={
                "title": "Repair brake warning",
                "description": "Diagnose and repair the critical brake defect.",
                "priority": "critical",
            },
        )
    _clear()

    assert response.status_code == 201
    assert service.last_organization_id == ORGANIZATION_ID
    assert service.last_create is not None
    assert service.last_create.source_defect_id == DEFECT_ID
    assert service.last_create.currency == "CAD"


def test_assigned_mechanic_can_request_operational_transition() -> None:
    client, service = _client(MembershipRole.MECHANIC)
    with client:
        response = client.post(
            f"/api/v1/work-orders/{ORDER_ID}/transitions",
            headers={"Authorization": "Bearer valid"},
            json={"version": 1, "status": "in_progress", "note": "Work started"},
        )
    _clear()

    assert response.status_code == 200
    assert response.json()["status"] == "in_progress"
    assert service.last_transition_role is MembershipRole.MECHANIC


def test_stale_work_order_transition_returns_conflict() -> None:
    client, _ = _client(MembershipRole.MANAGER)
    with client:
        response = client.post(
            f"/api/v1/work-orders/{ORDER_ID}/transitions",
            headers={"Authorization": "Bearer valid"},
            json={"version": 99, "status": "triaged"},
        )
    _clear()

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "STALE_VERSION"


def test_driver_cannot_read_work_orders() -> None:
    client, _ = _client(MembershipRole.DRIVER)
    with client:
        response = client.get("/api/v1/work-orders", headers={"Authorization": "Bearer valid"})
    _clear()

    assert response.status_code == 403


def _client(role: MembershipRole) -> tuple[TestClient, FakeWorkOrderService]:
    service = FakeWorkOrderService()
    app.dependency_overrides[get_auth_service] = lambda: FakeAuthService(role)
    app.dependency_overrides[get_work_order_service] = lambda: service
    return TestClient(app), service


def _clear() -> None:
    app.dependency_overrides.clear()


def _order(
    *,
    status: WorkOrderStatus = WorkOrderStatus.REPORTED,
    version: int = 1,
) -> WorkOrder:
    return WorkOrder(
        id=ORDER_ID,
        organization_id=ORGANIZATION_ID,
        number=1,
        vehicle_id=VEHICLE_ID,
        source_defect_id=DEFECT_ID,
        maintenance_schedule_id=None,
        title="Repair brake warning",
        description="Diagnose and repair the critical brake defect.",
        priority="critical",
        status=status,
        assigned_mechanic_membership_id=MEMBERSHIP_ID,
        labour_hours=Decimal("0.00"),
        labour_cost=Decimal("0.00"),
        parts_cost=Decimal("0.00"),
        currency="CAD",
        opened_at=NOW,
        version=version,
        created_by_user_id=USER_ID,
        created_at=NOW,
        updated_at=NOW,
    )
