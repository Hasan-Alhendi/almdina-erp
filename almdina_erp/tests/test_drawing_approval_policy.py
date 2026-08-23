from __future__ import annotations

import pytest

from almdina_erp.almdina_erp.application.security.drawing_approval_policy import (
    DrawingApprovalDenied,
    DrawingApprovalState,
    approval_warning,
    validate_drawing_approval,
)


def _state(**overrides: str) -> DrawingApprovalState:
    values = {
        "status": "At Drawing",
        "production_path": "Drawing",
        "current_department": "رسم",
        "approved_plan": "",
    }
    values.update(overrides)
    return DrawingApprovalState(**values)


def test_drawing_approval_has_no_assignment_requirement():
    state = _state()
    validate_drawing_approval(state)
    assert not hasattr(state, "current_assignee")
    assert not hasattr(state, "session_user")


def test_existing_approval_returns_warning_without_blocking():
    state = _state(approved_plan="PLAN-0001")
    validate_drawing_approval(state)
    assert approval_warning(state) == "already_approved"


def test_approval_is_rejected_outside_drawing_stage():
    with pytest.raises(DrawingApprovalDenied) as error:
        validate_drawing_approval(
            _state(
                status="At CNC",
                production_path="Drawing",
                current_department="CNC",
            )
        )
    assert error.value.code == "not_at_drawing"
