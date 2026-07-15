from fleetpulse.work_orders.service import LEGAL_TRANSITIONS, MECHANIC_TRANSITIONS
from fleetpulse.work_orders.types import WorkOrderStatus


def test_work_order_state_machine_requires_verification_before_close() -> None:
    assert WorkOrderStatus.VERIFIED in LEGAL_TRANSITIONS[WorkOrderStatus.COMPLETED]
    assert WorkOrderStatus.CLOSED not in LEGAL_TRANSITIONS[WorkOrderStatus.COMPLETED]
    assert LEGAL_TRANSITIONS[WorkOrderStatus.VERIFIED] == {WorkOrderStatus.CLOSED}
    assert not LEGAL_TRANSITIONS[WorkOrderStatus.CLOSED]


def test_mechanic_transitions_exclude_verification_and_closure() -> None:
    assert {
        WorkOrderStatus.IN_PROGRESS,
        WorkOrderStatus.WAITING_PARTS,
        WorkOrderStatus.COMPLETED,
    } == MECHANIC_TRANSITIONS
