from __future__ import annotations

import runpy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ORDER_PY = (
    ROOT
    / "almdina_erp"
    / "doctype"
    / "door_cutting_order"
    / "door_cutting_order.py"
)
CONTROLLER_PY = (
    ROOT
    / "almdina_erp"
    / "doctype"
    / "door_cutting_order"
    / "door_cutting_order_controller.py"
)
SAVE_USE_CASE = (
    ROOT / "almdina_erp" / "application" / "orders" / "process_order_save.py"
)
PLAN_ADAPTER = (
    ROOT
    / "almdina_erp"
    / "infrastructure"
    / "frappe"
    / "orders"
    / "plan_adapter.py"
)
EDGE_REPOSITORY = (
    ROOT
    / "almdina_erp"
    / "infrastructure"
    / "frappe"
    / "orders"
    / "edge_profile_repository.py"
)
PLAN_PERMISSION_SERVICE = (
    ROOT / "almdina_erp" / "services" / "order_plan_permission_service.py"
)
PLAN_COMMAND_SERVICE = (
    ROOT / "almdina_erp" / "services" / "cutting_plan_command_service.py"
)
FRONTEND_ASSETS = ROOT / "frontend_assets.py"
HOOKS = ROOT / "hooks.py"
FAST_SAVE_JS = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "cutting_plan"
    / "door_cutting_order_fast_save_ux.js"
)
PLAN_JS = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "cutting_plan"
    / "door_cutting_order_plan_ux.js"
)


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_canonical_base_is_thin_and_delegates_save_ownership():
    source = _text(ORDER_PY)
    assert "class DoorCuttingOrder(Document)" in source
    assert "process_order_save(self._gateway())" in source
    assert "FrappeDoorCuttingOrderSaveGateway" in source
    assert "FrappeOrderPlanAdapter" in source
    assert "def optimize_plan" not in source
    assert "optimize_plan(" not in source
    assert "frappe.db.get_value(" not in source
    assert "frappe.get_all(" not in source
    assert len(source.splitlines()) < 190


def test_active_controller_keeps_save_orchestration_outside_the_doctype_base():
    source = _text(CONTROLLER_PY)
    assert "process_order_save(self._gateway())" in source
    assert "FrappeDoorCuttingOrderSaveGateway" in source
    assert "class DoorCuttingOrderController(DoorCuttingOrder)" in source


def test_save_use_case_runs_optimizer_only_on_explicit_recalculation():
    source = _text(SAVE_USE_CASE)
    assert "gateway.force_recalculation_requested()" in source
    assert "gateway.calculate_cutting_plan(input_fingerprint)" in source
    assert "gateway.can_reuse_current_plan(input_fingerprint)" in source
    assert "gateway.refresh_current_plan(input_fingerprint)" in source
    assert "gateway.invalidate_current_plan()" in source


def test_explicit_recalculation_is_owned_by_capability_protected_service():
    facade = _text(PLAN_PERMISSION_SERVICE)
    command = _text(PLAN_COMMAND_SERVICE)

    assert "return recalculate_order_plan(" in facade
    assert "Capability.RECALCULATE_PLAN" in command
    assert "_assert_recalculation_state(order)" in command
    assert "recalculate_system_plan(" in command
    assert "doc.save(ignore_permissions=True)" not in command

    hooks = runpy.run_path(str(HOOKS))
    assert hooks["override_whitelisted_methods"][
        "almdina_erp.almdina_erp.doctype.door_cutting_order."
        "door_cutting_order.recalculate_order"
    ] == (
        "almdina_erp.almdina_erp.services.order_plan_permission_service."
        "recalculate_order"
    )


def test_plan_fingerprint_and_optimizer_live_in_focused_plan_adapter():
    source = _text(PLAN_ADAPTER)
    assert "fingerprint_payload" in source
    assert "def plan_input_fingerprint" in source
    assert "def calculate_cutting_plan" in source
    assert "optimize_order_plan(" in source
    assert "domain_cutting_engine" in source


def test_edge_profile_repository_owns_batched_edge_master_reads():
    source = _text(EDGE_REPOSITORY)
    assert "class FrappeEdgeProfileRepository" in source
    assert "frappe.get_all(" in source
    assert 'filters={"name": ["in", sorted(names)]}' in source
    assert "rate_usd_per_meter" in source


def test_fast_save_assets_use_feature_owned_manifest_paths_and_ordering():
    assets = runpy.run_path(str(FRONTEND_ASSETS))
    scripts = assets["doctype_js"]["Door Cutting Order"]
    plan_path = (
        "public/js/door_cutting_order/cutting_plan/"
        "door_cutting_order_plan_ux.js"
    )
    fast_path = (
        "public/js/door_cutting_order/cutting_plan/"
        "door_cutting_order_fast_save_ux.js"
    )
    assert plan_path in scripts
    assert fast_path in scripts
    assert scripts.index(plan_path) < scripts.index(fast_path)
    assert PLAN_JS.is_file()
    assert FAST_SAVE_JS.is_file()


def test_fast_save_script_keeps_checkpoint_then_plan_command_flow():
    fast_source = _text(FAST_SAVE_JS)
    plan_source = _text(PLAN_JS)

    assert "persistOrderEditCheckpoint" in fast_source
    assert "markOrderInputPlanStale" in fast_source
    assert "markOptimizerPlanStale" in fast_source
    assert "await frm.save()" not in fast_source
    assert "door_cutting_order.recalculate_order" not in fast_source

    assert "runRecalculation" in plan_source
    assert "controls.runRecalculation(frm)" in plan_source
    assert "frm.save()/frm.call()" in plan_source


def test_invoice_print_remains_available_while_plan_is_stale():
    source = _text(FAST_SAVE_JS)
    assert 'event.target.closest(".dco-print-customer-invoice")' not in source
    assert "dco-cost-plan-stale" not in source
    assert "is-plan-stale" not in source
    assert "أعد حساب خطة القص أولًا" not in source
