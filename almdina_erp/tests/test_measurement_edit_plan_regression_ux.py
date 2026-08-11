from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_JS = ROOT / "public" / "js"


def source(name: str) -> str:
    return (PUBLIC_JS / name).read_text(encoding="utf-8")


def test_special_door_pricing_does_not_block_ordinary_save() -> None:
    cost_permissions = source("door_cutting_order_cost_permissions_ux.js")

    assert "pendingCustomEdgePriceLabels" not in cost_permissions
    assert "أدخل أسعار قشاط الدرفات الخاصة ودرفات الزاوية المقصوصة قبل الحفظ" not in cost_permissions
    assert "frappe.validated = false" not in cost_permissions


def test_recalculation_persists_pending_order_inputs_before_server_plan_call() -> None:
    plan_controls = source("door_cutting_order_plan_controls_ux.js")
    fast_save = source("door_cutting_order_fast_save_ux.js")
    revision = source("door_cutting_order_revision_ux.js")

    assert "async function persistPendingOrderInputs(frm)" in fast_save
    assert "editPolicy.persistOrderEditCheckpoint(frm)" in fast_save
    assert "frm.save" not in fast_save
    assert "async function persistOrderEditCheckpoint(frm)" in revision
    assert "await frm.save();" in revision
    assert "frappe.almdina.persistOrderEditCheckpoint = persistOrderEditCheckpoint" in revision
    assert "__almdina_preserve_edit_session_after_save" in revision
    assert "frm.__almdina_pending_order_input_persistence = true" in fast_save
    assert "piece_type(frm) { markOrderInputPlanStale(frm); }" in fast_save
    assert "fastSave.persistPendingOrderInputs(frm)" in plan_controls
    assert "frm.save" not in plan_controls

    run_body = plan_controls.split("async function runRecalculation(frm)", 1)[1]
    persist_pos = run_body.index("await persistPendingOrderInputs(frm)")
    recalc_pos = run_body.index("method: RECALCULATE_METHOD")
    assert persist_pos < recalc_pos


def test_optimizer_only_recalculation_does_not_require_order_save() -> None:
    fast_save = source("door_cutting_order_fast_save_ux.js")

    mark_order_body = fast_save.split("function markOrderInputPlanStale(frm)", 1)[1].split(
        "function markOptimizerPlanStale(frm)", 1
    )[0]
    mark_optimizer_body = fast_save.split("function markOptimizerPlanStale(frm)", 1)[1].split(
        "async function", 1
    )[0]
    assert "__almdina_pending_order_input_persistence = true" in mark_order_body
    assert "__almdina_pending_order_input_persistence" not in mark_optimizer_body


def test_edge_rendering_uses_one_structural_observer_instead_of_feedback_observers() -> None:
    operator_patch = source("door_cutting_order_operator_ux_patch.js")

    assert "disconnectCompetingEdgeObservers" in operator_patch
    assert '"_dcoSideEdgeObserver"' in operator_patch
    assert '"_dcoCompactEdgeProfileControlsObserver"' in operator_patch
    assert "structuralMeasurementMutation" in operator_patch
    assert "__dcoEdgeStructureObserver" in operator_patch
    assert "observer.observe(wrapper, { childList: true, subtree: true })" in operator_patch
