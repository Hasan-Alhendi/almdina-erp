from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_JS = ROOT / "public" / "js"
PIECE_POLICY_ADAPTER = (
    ROOT
    / "almdina_erp"
    / "infrastructure"
    / "frappe"
    / "orders"
    / "piece_policy_adapter.py"
)


def source(name: str) -> str:
    return (PUBLIC_JS / name).read_text(encoding="utf-8")


def test_special_door_pricing_does_not_block_ordinary_save() -> None:
    cost_permissions = source("door_cutting_order/costing/door_cutting_order_cost_permissions_ux.js")
    adapter = PIECE_POLICY_ADAPTER.read_text(encoding="utf-8")
    validate_rows = adapter.split("def validate_rows(self)", 1)[1].split(
        "def ensure_documented(self)", 1
    )[0]

    assert "pendingCustomEdgePriceLabels" not in cost_permissions
    assert "أدخل أسعار قشاط الدرفات الخاصة ودرفات الزاوية المقصوصة قبل الحفظ" not in cost_permissions
    assert "frappe.validated = false" not in cost_permissions
    assert "ensure_custom_edge_prices" not in validate_rows
    # The explicit financial gate is retained for invoice/final-price flows.
    assert "def ensure_custom_edge_prices(self)" in adapter


def test_preview_persists_pending_order_inputs_before_server_preview_call() -> None:
    plan_controls = source("door_cutting_order/cutting_plan/door_cutting_order_plan_controls_ux.js")
    plan_api = source("door_cutting_order/cutting_plan/door_cutting_order_plan_workspace_api.js")
    fast_save = source("door_cutting_order/cutting_plan/door_cutting_order_fast_save_ux.js")
    revision = source("door_cutting_order/core/door_cutting_order_revision_ux.js")

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
    assert "RECALCULATE_METHOD" in plan_api
    assert "frappe.call" not in plan_controls
    assert "AlmdinaPlanPreviewSession" in plan_controls

    run_body = plan_controls.split("async function runRecalculation(frm)", 1)[1]
    prepare_pos = run_body.index("await preparePlanInputs(frm)")
    persist_pos = run_body.index("await persistPendingOrderInputs(frm)")
    preview_pos = run_body.index("await previews.preview(frm, settings)")
    assert prepare_pos < persist_pos < preview_pos
    assert "transport.recalculate(frm.doc.name, settings)" not in run_body


def test_optimizer_only_recalculation_does_not_require_order_save() -> None:
    fast_save = source("door_cutting_order/cutting_plan/door_cutting_order_fast_save_ux.js")

    mark_order_body = fast_save.split("function markOrderInputPlanStale(frm)", 1)[1].split(
        "function markOptimizerPlanStale(frm)", 1
    )[0]
    mark_optimizer_body = fast_save.split("function markOptimizerPlanStale(frm)", 1)[1].split(
        "async function", 1
    )[0]
    assert "__almdina_pending_order_input_persistence = true" in mark_order_body
    assert "__almdina_pending_order_input_persistence" not in mark_optimizer_body


def test_kerf_and_trim_follow_focused_optimizer_plan_staleness() -> None:
    fast_save = source("door_cutting_order/cutting_plan/door_cutting_order_fast_save_ux.js")
    field_access = source(
        "door_cutting_order/cutting_plan/door_cutting_order_plan_field_access_adapter.js"
    )

    assert "kerf_mm(frm) { markOptimizerPlanStale(frm); }" in fast_save
    assert "trim_margin_mm(frm) { markOptimizerPlanStale(frm); }" in fast_save
    assert "kerf_mm(frm) { markOrderInputPlanStale(frm); }" not in fast_save
    assert "trim_margin_mm(frm) { markOrderInputPlanStale(frm); }" not in fast_save

    # The final field-state bridge runs after order edit-session locking and
    # delegates the actual decision back to PlanControls. Kerf/trim therefore do
    # not require an order-save checkpoint or broad EDIT_ORDER authority.
    assert "controls.applyOptimizerFieldAccess(frm)" in field_access
    assert "almdina_edit_session_changed(frm) { schedule(frm); }" in field_access
    assert "refresh_plan_controls(frm) { schedule(frm); }" in field_access
    assert "frm.perm" not in field_access


def test_edge_rendering_uses_one_structural_observer_instead_of_feedback_observers() -> None:
    edge_owner = source(
        "door_cutting_order/order_entry/edge_banding/door_cutting_order_edge_render_owner.js"
    )
    removed_patch = PUBLIC_JS / "door_cutting_order/order_entry/door_cutting_order_operator_ux_patch.js"

    assert not removed_patch.exists()
    assert "function disconnectLegacyObservers(wrapper)" in edge_owner
    assert '"_dcoSideEdgeObserver"' in edge_owner
    assert '"_dcoCompactEdgeProfileControlsObserver"' in edge_owner
    assert "function structuralMeasurementMutation(mutation)" in edge_owner
    assert "const observer = new MutationObserver" in edge_owner
    assert edge_owner.count("new MutationObserver") == 1
    assert "frm.__dcoEdgeRenderObserver" in edge_owner
    assert "observer.observe(wrapper, { childList: true, subtree: true })" in edge_owner

    render_body = edge_owner.split("function renderDecorations(frm)", 1)[1].split(
        "function scheduleStructuralRefresh(frm)", 1
    )[0]
    assert "const wrapper = measurementWrapper(frm);" in render_body
    assert "multiEdge.schedule(frm);" in render_body
    assert "controls.schedule(frm);" in render_body
    assert render_body.index("multiEdge.schedule(frm);") < render_body.index("controls.schedule(frm);")
    assert "disconnectLegacyObservers(wrapper);" in render_body


def test_special_edge_visual_highlight_is_scoped_to_special_rows() -> None:
    edge_owner = source(
        "door_cutting_order/order_entry/edge_banding/door_cutting_order_edge_render_owner.js"
    )

    assert 'STYLE_ID = "dco-special-edge-visual-guard-css"' in edge_owner
    assert "tr:not(.dco-special-row)" in edge_owner
    assert ".is-edge-missing.is-checked" in edge_owner
    assert "tr.dco-special-row" in edge_owner
    assert "background:#b5701c!important" in edge_owner
    assert "background:var(--primary,#2490ef)!important" in edge_owner
