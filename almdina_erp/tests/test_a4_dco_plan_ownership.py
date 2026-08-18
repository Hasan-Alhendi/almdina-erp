from __future__ import annotations

from pathlib import Path

from almdina_erp.almdina_erp.domain.cutting.plan_freshness import (
    decide_draft_plan_freshness,
)
from almdina_erp.almdina_erp.domain.cutting.plan_lifecycle import APPROVED, DRAFT


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "almdina_erp"
PROCESS_ORDER_SAVE = APP / "application" / "orders" / "process_order_save.py"
SAVE_GATEWAY = APP / "infrastructure" / "frappe" / "orders" / "save_gateway.py"
BOARD_ADAPTER = APP / "infrastructure" / "frappe" / "orders" / "board_input_adapter.py"
CONTROLLER = (
    APP
    / "doctype"
    / "door_cutting_order"
    / "door_cutting_order_controller.py"
)
INVALIDATION_SERVICE = APP / "services" / "cutting_plan_invalidation_service.py"


def source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_order_save_application_use_case_has_no_cutting_plan_orchestration() -> None:
    text = source(PROCESS_ORDER_SAVE)
    for retired_contract in (
        "plan_input_fingerprint",
        "force_recalculation_requested",
        "can_reuse_current_plan",
        "calculate_cutting_plan",
        "refresh_current_plan",
        "invalidate_current_plan",
        "sanitize_plan_snapshots",
        "OrderSaveOutcome",
        "plan_action",
        "validate_numeric_inputs",
    ):
        assert retired_contract not in text

    assert "calculate_cut_dimensions" in text
    assert "calculate_piece_costs" in text


def test_order_save_gateway_has_no_plan_adapter_or_plan_owned_numeric_validation() -> None:
    text = source(SAVE_GATEWAY)
    assert "FrappeOrderBoardInputAdapter" in text
    assert "self.board.load_snapshot()" in text
    assert "validate_numeric_inputs" not in text
    assert "FrappeCutDimensionPlanAdapter" not in text
    assert "sanitize_plan_snapshot_json" not in text
    assert "force_cutting_plan_recalculation" not in text
    assert "can_reuse_current_plan" not in text
    assert "calculate_cutting_plan" not in text
    assert "refresh_current_plan" not in text
    assert "invalidate_current_plan" not in text
    assert "self.plan" not in text


def test_board_requirements_adapter_has_no_plan_or_cost_inputs() -> None:
    text = source(BOARD_ADAPTER)
    for order_field in (
        "board_description",
        "board_length_cm",
        "board_width_cm",
        "full_board_length_mm",
        "full_board_width_mm",
    ):
        assert order_field in text
    for plan_owned in (
        "kerf_mm",
        "trim_margin_mm",
        "optimization_time_limit_sec",
        "board_rate_usd",
        "cutting_cost_per_board_usd",
        "usable_board",
    ):
        assert plan_owned not in text


def test_active_controller_invalidates_plans_only_after_order_persistence() -> None:
    text = source(CONTROLLER)
    validate = text.split("def validate(self)", 1)[1].split("def on_update(self)", 1)[0]
    on_update = text.split("def on_update(self)", 1)[1].split(
        "def ensure_special_shapes_documented", 1
    )[0]

    assert "process_order_save" in validate
    assert "invalidate_stale_draft_plans" not in validate
    assert "invalidate_stale_draft_plans" in on_update
    assert "recalculate" not in on_update.lower()
    assert "save(" not in on_update


def test_invalidation_service_is_focused_and_never_runs_optimizer() -> None:
    text = source(INVALIDATION_SERVICE)
    assert '"status": DRAFT' in text
    assert "plan_input_fingerprint" in text
    assert "decide_draft_plan_freshness" in text
    assert '"plan_needs_recalculation"' in text
    assert "frappe.db.set_value" in text
    assert "update_modified=False" in text

    for forbidden in (
        "ignore_permissions",
        ".save(",
        "optimize_order_plan",
        "calculate_system_plan",
        "apply_validated_dxf_snapshot",
        '"status": APPROVED',
    ):
        assert forbidden not in text


def test_approved_plan_mismatch_only_raises_order_stale_projection() -> None:
    text = source(INVALIDATION_SERVICE)
    approved_block = text.split("approved_name =", 1)[1].split(
        "if requires_recalculation:", 1
    )[0]
    assert 'frappe.db.exists("Cutting Plan", approved_name)' in approved_block
    assert "_plan_matches_order(order, approved_plan)" in approved_block
    assert "requires_recalculation = True" in approved_block
    assert "frappe.db.set_value" not in approved_block
    assert ".save(" not in approved_block


def test_fresh_draft_requires_no_write() -> None:
    decision = decide_draft_plan_freshness(
        status=DRAFT,
        stored_fingerprint="same",
        expected_fingerprint="same",
        already_needs_recalculation=False,
    )
    assert not decision.should_invalidate
    assert decision.reason == "fresh"


def test_changed_draft_is_marked_stale() -> None:
    decision = decide_draft_plan_freshness(
        status=DRAFT,
        stored_fingerprint="before",
        expected_fingerprint="after",
        already_needs_recalculation=False,
    )
    assert decision.should_invalidate
    assert decision.reason == "order_requirements_changed"


def test_already_stale_draft_is_idempotent() -> None:
    decision = decide_draft_plan_freshness(
        status=DRAFT,
        stored_fingerprint="before",
        expected_fingerprint="after",
        already_needs_recalculation=True,
    )
    assert not decision.should_invalidate
    assert decision.reason == "already_stale"


def test_approved_plan_is_immutable_even_when_order_fingerprint_differs() -> None:
    decision = decide_draft_plan_freshness(
        status=APPROVED,
        stored_fingerprint="before",
        expected_fingerprint="after",
        already_needs_recalculation=False,
    )
    assert not decision.should_invalidate
    assert decision.reason == "immutable_revision"
