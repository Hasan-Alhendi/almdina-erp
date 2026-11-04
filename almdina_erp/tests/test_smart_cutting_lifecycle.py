"""New execution selects Smart without changing historical read contracts."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from almdina_erp.tests.frappe_test_stub import install_if_unavailable
install_if_unavailable()

from almdina_erp.almdina_erp.domain.cutting.plan_settings import (
    normalize_plan_settings, settings_for_system_search,
)
from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe import cutting_plan_workspace as workspace
from almdina_erp.almdina_erp.services import cutting_plan_command_service as commands
from almdina_erp.tests.test_plan_fingerprint_compatibility import golden_case


def test_new_search_policy_only_replaces_mode():
    original = normalize_plan_settings(optimization_mode="deep_search", machine_type="Panel Saw",
        optimization_time_limit_sec=2.25, kerf_mm=0, preferred_trim_mm=0)
    smart = settings_for_system_search(original)
    assert smart.optimization_mode == "smart"
    assert original.optimization_mode == "deep_search"
    assert (smart.machine_type, smart.optimization_time_limit_sec, smart.kerf_mm, smart.preferred_trim_mm) == (
        original.machine_type, original.optimization_time_limit_sec, 0, 0)


def test_calculation_selects_smart_before_fingerprinting():
    _, order, plan = golden_case()
    original = deepcopy(plan)
    before = workspace.plan_input_fingerprint(order, plan)
    captured = []
    def calculate(command, **kwargs):
        captured.append(command)
        return Mock()
    factory = SimpleNamespace(optimal_search_piece_limit=20, min_remnant_width_mm=300,
                              min_remnant_length_mm=300, min_remnant_area_m2=.09)
    with patch.object(workspace.frappe, "get_cached_doc", return_value=factory, create=True), \
         patch.object(workspace, "optimize_order_plan", side_effect=calculate), \
         patch.object(workspace, "apply_calculation_outcome"):
        workspace.calculate_system_plan(order, plan)
    assert plan.optimization_mode == captured[0].optimizer.selected_mode == "smart"
    assert captured[0].input_fingerprint == workspace.plan_input_fingerprint(order, plan)
    assert captured[0].input_fingerprint != before
    assert vars(plan) == vars(original) | {"optimization_mode": "smart"}


@pytest.mark.parametrize("updates,needs_edit", [
    ({"packing_mode": "smart"}, False), ({"packing_mode": "Auto"}, False),
    ({"kerf_mm": 0}, True), ({"trim_margin_mm": 0}, True),
    ({"cutting_machine_type": "Panel Saw"}, True),
    ({"optimization_time_limit_sec": 3}, True),
])
def test_recalculation_mode_policy_never_grants_settings_permission(updates, needs_edit):
    _, order, plan = golden_case()
    plan.name = "CP-SMART"
    plan.kerf_mm = 3
    plan.trim_margin_mm = 5
    repo = Mock()
    repo.ensure_system_draft.return_value = plan
    def require(_order, capability, **kwargs):
        if capability == Capability.EDIT_OPTIMIZER_SETTINGS:
            raise PermissionError("edit denied")
    with patch.object(commands, "require_cutting_plan_capability", side_effect=require), \
         patch.object(commands, "FrappeCuttingPlanCommandRepository", return_value=repo), \
         patch.object(commands, "initialize_draft_plan_cost_snapshot"), \
         patch.object(commands, "backfill_piece_instance_ids"), \
         patch.object(commands, "calculate_system_plan") as calculate, \
         patch.object(commands, "apply_plan_costs"), \
         patch.object(commands, "factory_execution_edge_cost"), \
         patch.object(commands, "refresh_order_commercial_totals"), \
         patch.object(commands, "plan_payload", return_value={}), \
         patch("almdina_erp.almdina_erp.services.final_price_approval_service.maybe_invalidate_final_price_approval"):
        if needs_edit:
            with pytest.raises(PermissionError, match="edit denied"):
                commands.recalculate_system_plan(order, updates)
            calculate.assert_not_called()
            repo.save_document.assert_not_called()
        else:
            result = commands.recalculate_system_plan(order, updates)
            assert result["changed_fields"] == []
            calculate.assert_called_once_with(order, plan)
            repo.save_document.assert_called_once_with(plan)
