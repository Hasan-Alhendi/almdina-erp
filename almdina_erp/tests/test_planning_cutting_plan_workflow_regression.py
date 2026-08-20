from __future__ import annotations

from almdina_erp.almdina_erp.domain.orders.planning_handoff_policy import (
    PlanningHandoffFacts,
    decide_planning_handoff,
)
from almdina_erp.almdina_erp.domain.orders.production_authorization import (
    ProductionActionFacts,
    decide_production_action,
)
from almdina_erp.almdina_erp.domain.orders.stage_assignment_access import (
    decide_stage_assignment_access,
)
from almdina_erp.almdina_erp.domain.security.authorization import Capability


def _dispatch(*, planning_first: bool, has_plan: bool, stale: bool = False):
    return decide_production_action(
        Capability.DISPATCH_ORDER,
        capabilities=(Capability.DISPATCH_ORDER,),
        facts=ProductionActionFacts(
            order_status="Draft",
            route_starts_with_planning=planning_first,
            has_cutting_plan=has_plan,
            plan_needs_recalculation=stale,
        ),
    )


def test_planning_first_dispatch_does_not_require_a_cutting_plan() -> None:
    decision = _dispatch(planning_first=True, has_plan=False)
    assert decision.allowed is True
    assert decision.code == "allowed"


def test_direct_production_dispatch_requires_current_cutting_plan() -> None:
    missing = _dispatch(planning_first=False, has_plan=False)
    assert missing.allowed is False
    assert missing.code == "missing_cutting_plan"

    stale = _dispatch(planning_first=False, has_plan=True, stale=True)
    assert stale.allowed is False
    assert stale.code == "stale_cutting_plan"


def test_operational_role_never_replaces_required_capability() -> None:
    decision = decide_production_action(
        Capability.HANDOFF_ASSIGNED_STAGE,
        capabilities=(),
        facts=ProductionActionFacts(
            order_status="At Drawing",
            current_stage_name="STAGE-1",
            stage_name="STAGE-1",
            stage_status="In Progress",
            assigned_to="designer@example.com",
            actor="designer@example.com",
            operational_role="Designer",
            actor_roles=("Designer",),
        ),
    )
    assert decision.allowed is False
    assert decision.code == "missing_capability"


def test_capability_never_replaces_current_assignment() -> None:
    decision = decide_production_action(
        Capability.HANDOFF_ASSIGNED_STAGE,
        capabilities=(Capability.HANDOFF_ASSIGNED_STAGE,),
        facts=ProductionActionFacts(
            order_status="At Drawing",
            current_stage_name="STAGE-1",
            stage_name="STAGE-1",
            stage_status="In Progress",
            assigned_to="designer-a@example.com",
            actor="designer-b@example.com",
            operational_role="Designer",
            actor_roles=("Designer",),
        ),
    )
    assert decision.allowed is False
    assert decision.code == "not_assigned"


def test_stage_scoped_mutation_is_assignment_based_not_role_based() -> None:
    allowed = decide_stage_assignment_access(
        actor="designer@example.com",
        assigned_to="designer@example.com",
        has_current_stage=True,
        has_production_path=True,
    )
    assert allowed.allowed is True

    denied = decide_stage_assignment_access(
        actor="other@example.com",
        assigned_to="designer@example.com",
        has_current_stage=True,
        has_production_path=True,
    )
    assert denied.allowed is False
    assert denied.code == "not_assigned"


def test_planning_handoff_reports_missing_approval_precisely() -> None:
    decision = decide_planning_handoff(
        PlanningHandoffFacts(
            is_planning_stage=True,
            approved_plan_name=None,
            has_current_approved_plan=False,
            plan_needs_recalculation=False,
        )
    )
    assert decision.allowed is False
    assert decision.code == "plan_not_approved"


def test_planning_handoff_reports_stale_approved_plan_before_generic_approval_error() -> None:
    decision = decide_planning_handoff(
        PlanningHandoffFacts(
            is_planning_stage=True,
            approved_plan_name="CP-0001",
            has_current_approved_plan=False,
            plan_needs_recalculation=True,
        )
    )
    assert decision.allowed is False
    assert decision.code == "approved_plan_stale"
    assert "أعد حسابها" in decision.reason


def test_planning_handoff_allows_exact_current_approved_plan() -> None:
    decision = decide_planning_handoff(
        PlanningHandoffFacts(
            is_planning_stage=True,
            approved_plan_name="CP-0001",
            has_current_approved_plan=True,
            plan_needs_recalculation=False,
        )
    )
    assert decision.allowed is True
    assert decision.code == "allowed"
