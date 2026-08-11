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


def test_recalculation_persists_dirty_measurement_rows_before_server_plan_call() -> None:
    plan_controls = source("door_cutting_order_plan_controls_ux.js")

    helper = "async function persistDirtyOrderBeforeRecalculation(frm)"
    assert helper in plan_controls
    assert "await frm.save();" in plan_controls
    assert "await persistDirtyOrderBeforeRecalculation(frm)" in plan_controls

    run_body = plan_controls.split("async function runRecalculation(frm)", 1)[1]
    save_pos = run_body.index("await persistDirtyOrderBeforeRecalculation(frm)")
    recalc_pos = run_body.index("method: RECALCULATE_METHOD")
    assert save_pos < recalc_pos


def test_edge_rendering_uses_one_structural_observer_instead_of_feedback_observers() -> None:
    operator_patch = source("door_cutting_order_operator_ux_patch.js")

    assert "disconnectCompetingEdgeObservers" in operator_patch
    assert '"_dcoSideEdgeObserver"' in operator_patch
    assert '"_dcoCompactEdgeProfileControlsObserver"' in operator_patch
    assert "structuralMeasurementMutation" in operator_patch
    assert "__dcoEdgeStructureObserver" in operator_patch
    assert "observer.observe(wrapper, { childList: true, subtree: true })" in operator_patch
