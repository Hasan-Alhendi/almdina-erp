from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UX = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "production"
    / "door_cutting_order_intake_planning_ux.js"
)
SHOP_FLOOR_UX = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "production"
    / "shop_floor_order_ux.js"
)
DISPATCH_SERVICE = (
    ROOT
    / "almdina_erp"
    / "services"
    / "order_dispatch_service.py"
)
WORKFLOW_SYNC = (
    ROOT
    / "almdina_erp"
    / "infrastructure"
    / "frappe"
    / "order_workflow_stage_sync.py"
)
LIFECYCLE = ROOT / "lifecycle.py"


def test_intake_planning_ux_uses_server_plan_without_starting_production() -> None:
    source = UX.read_text(encoding="utf-8")

    assert source.startswith("(() => {")
    assert source.rstrip().endswith("})();")
    assert "order_intake_service.get_finish_data_entry_options" in source
    assert "order_intake_service.finish_data_entry" in source
    assert '__("إنهاء إدخال البيانات")' in source
    assert '__("تعديل خطة الإرسال")' in source
    assert "dispatch_order" not in source
    assert "Production Stage" not in source
    assert "setTimeout(" not in source


def test_intake_planning_ux_retires_legacy_dispatch_button_during_intake() -> None:
    source = UX.read_text(encoding="utf-8")

    assert 'frm.remove_custom_button(__("إرسال للإنتاج"))' in source
    assert 'stage === DATA_ENTRY' in source
    assert 'stage === READY_TO_DISPATCH' in source


def test_intake_planning_ux_hides_plan_actions_if_real_production_already_started() -> None:
    source = UX.read_text(encoding="utf-8")

    assert "function productionStarted(frm)" in source
    assert "frm.doc.production_path || frm.doc.current_production_stage" in source
    assert "frm.is_new() || !canEditOrder(frm) || productionStarted(frm)" in source


def test_intake_actions_reconcile_when_permissions_become_ready() -> None:
    source = UX.read_text(encoding="utf-8")

    assert "function reconcileIntakeActions(frm)" in source
    assert 'window.addEventListener("almdina:permissions-updated"' in source
    assert "reconcileIntakeActions(frm);" in source
    assert 'frappe.ui.form.on("Door Cutting Order", { refresh: reconcileIntakeActions });' in source
    assert "window.AlmdinaOrderIntakePlanningUX = Object.freeze" in source
    assert "function removeIntakeActions(frm)" in source
    assert 'frm.remove_custom_button(__(label))' in source
    assert "setTimeout(" not in source


def test_shop_floor_owner_never_recreates_legacy_dispatch_during_intake() -> None:
    source = SHOP_FLOOR_UX.read_text(encoding="utf-8")

    assert 'const INTAKE_WORKFLOW_STAGES = new Set(["DATA_ENTRY", "READY_TO_DISPATCH"]);' in source
    assert "function isIntakeManaged(frm)" in source
    assert 'frm.doc.workflow_stage || ""' in source
    assert 'if (frm.is_new() || !can(frm, "dispatch_order") || isIntakeManaged(frm)) return;' in source
    assert "!isIntakeManaged(frm)" in source


def test_legacy_dispatch_endpoint_enforces_intake_boundary_server_side() -> None:
    source = DISPATCH_SERVICE.read_text(encoding="utf-8")

    assert "assert_legacy_dispatch_allowed" in source
    assert "def _assert_legacy_dispatch_boundary(order: Any) -> None:" in source
    assert source.count("_assert_legacy_dispatch_boundary(order)") >= 2


def test_migrate_repairs_only_contradictory_intake_marker_before_backfill() -> None:
    sync_source = WORKFLOW_SYNC.read_text(encoding="utf-8")
    lifecycle_source = LIFECYCLE.read_text(encoding="utf-8")

    assert "def repair_started_orders_with_intake_stage() -> int:" in sync_source
    assert 'fields=["name", "production_path", "current_production_stage"]' in sync_source
    assert '"workflow_stage",\n            None,' in sync_source
    assert "repair_started_orders_with_intake_stage()" in lifecycle_source
    assert lifecycle_source.index("_repair_order_intake_state()") < lifecycle_source.index(
        "_backfill_order_intake_state()"
    )


def test_intake_planning_ux_blocks_unsaved_form_state_before_server_mutation() -> None:
    source = UX.read_text(encoding="utf-8")

    assert 'typeof frm.is_dirty === "function" && frm.is_dirty()' in source
    assert "Boolean(frm.doc.__unsaved)" in source
    assert "if (!requirePersistedFormState(frm)) return null;" in source
    assert "if (!requirePersistedFormState(frm)) return;" in source
    assert "if (hasUnsavedChanges(frm))" in source


def test_intake_planning_ux_rejects_stale_async_completions() -> None:
    source = UX.read_text(encoding="utf-8")

    assert "window.AlmdinaDocumentContext" in source
    assert "context.capture(frm)" in source
    assert "context.isCurrent(frm, token)" in source
    assert "const optionsToken = captureDocumentContext(frm);" in source
    assert "const mutationToken = captureDocumentContext(frm);" in source
    assert "if (!isCurrentDocumentContext(frm, optionsToken)) return;" in source
    assert "if (!isCurrentDocumentContext(frm, mutationToken)) return;" in source
