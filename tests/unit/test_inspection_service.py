import uuid
from decimal import Decimal

import pytest

from fleetpulse.defects.types import DefectSeverity
from fleetpulse.inspections.exceptions import (
    InvalidInspectionResponseError,
    MissingInspectionResponseError,
)
from fleetpulse.inspections.models import InspectionTemplateItem
from fleetpulse.inspections.service import (
    ReportedDefect,
    SubmitInspection,
    SubmittedResponse,
    hash_submission,
    validate_responses,
)
from fleetpulse.inspections.types import ResponseType


def test_submission_hash_is_stable_across_response_order() -> None:
    item_a, item_b = uuid.uuid4(), uuid.uuid4()
    first = _submission(
        [
            SubmittedResponse(template_item_id=item_a, result="pass"),
            SubmittedResponse(template_item_id=item_b, result="pass"),
        ]
    )
    second = SubmitInspection(
        vehicle_id=first.vehicle_id,
        template_id=first.template_id,
        odometer_km=first.odometer_km,
        notes=first.notes,
        responses=[
            SubmittedResponse(template_item_id=item_b, result="pass"),
            SubmittedResponse(template_item_id=item_a, result="pass"),
        ],
    )

    assert hash_submission(first) == hash_submission(second)


def test_failed_pass_fail_item_requires_defect_details() -> None:
    item = _item(required=True)

    with pytest.raises(InvalidInspectionResponseError):
        validate_responses([item], [SubmittedResponse(template_item_id=item.id, result="fail")])


def test_passed_item_rejects_defect_payload() -> None:
    item = _item(required=True)
    defect = ReportedDefect(
        category="brakes",
        description="Warning light remained on",
        severity=DefectSeverity.CRITICAL,
    )

    with pytest.raises(InvalidInspectionResponseError):
        validate_responses(
            [item],
            [SubmittedResponse(template_item_id=item.id, result="pass", defect=defect)],
        )


def test_required_template_item_must_be_answered() -> None:
    item = _item(required=True)

    with pytest.raises(MissingInspectionResponseError):
        validate_responses([item], [])


def _item(*, required: bool) -> InspectionTemplateItem:
    return InspectionTemplateItem(
        id=uuid.uuid4(),
        template_id=uuid.uuid4(),
        code="service_brakes",
        label="Service brakes respond normally",
        category="brakes",
        response_type=ResponseType.PASS_FAIL,
        required=required,
        sort_order=1,
    )


def _submission(responses: list[SubmittedResponse]) -> SubmitInspection:
    return SubmitInspection(
        vehicle_id=uuid.uuid4(),
        template_id=uuid.uuid4(),
        odometer_km=Decimal("123.4"),
        notes=None,
        responses=responses,
    )
