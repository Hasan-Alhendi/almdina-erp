from __future__ import annotations

from almdina_erp.almdina_erp.application.shop_floor.queries import _handoff_visibility
from almdina_erp.almdina_erp.domain.security.authorization import Capability


def _actions(*, handoff_allowed: bool) -> dict[str, dict[str, bool]]:
    return {
        Capability.HANDOFF_ASSIGNED_STAGE: {
            "allowed": handoff_allowed,
        }
    }


def test_authorized_handoff_stays_visible_while_planning_is_not_ready() -> None:
    actions = _actions(handoff_allowed=True)

    assert _handoff_visibility(actions, None) is True
    assert _handoff_visibility(actions, "plan_not_approved") is True
    assert _handoff_visibility(actions, "approved_plan_stale") is True


def test_handoff_visibility_never_bypasses_authorization() -> None:
    actions = _actions(handoff_allowed=False)

    assert _handoff_visibility(actions, None) is False
    assert _handoff_visibility(actions, "plan_not_approved") is False
    assert _handoff_visibility(actions, "approved_plan_stale") is False


def test_structural_route_failure_still_hides_handoff() -> None:
    actions = _actions(handoff_allowed=True)

    assert _handoff_visibility(actions, "invalid_route_stage") is False
