from __future__ import annotations

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
UX = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "production"
    / "door_cutting_order_intake_planning_ux.js"
)
SERVICE = ROOT / "almdina_erp" / "services" / "planned_dispatch_service.py"
APPLICATION = (
    ROOT
    / "almdina_erp"
    / "application"
    / "shop_floor"
    / "planned_dispatch.py"
)
TRACKING = (
    ROOT
    / "almdina_erp"
    / "infrastructure"
    / "frappe"
    / "order_tracking_repository.py"
)
STAGES = (
    ROOT
    / "almdina_erp"
    / "infrastructure"
    / "frappe"
    / "production_stage_repository.py"
)


def _dispatch_call_block(source: str) -> str:
    marker = "services.planned_dispatch_service.dispatch_planned_order"
    start = source.index(marker)
    end = source.index("}).then", start)
    return source[start:end]


def test_ready_ui_shows_plan_edit_and_real_dispatch_actions() -> None:
    source = UX.read_text(encoding="utf-8")

    assert 'const READY_TO_DISPATCH = "READY_TO_DISPATCH";' in source
    assert '__("تعديل خطة الإرسال")' in source
    assert '__("إرسال للإنتاج")' in source
    assert 'const DISPATCH_CAPABILITY = "dispatch_order";' in source
    assert "canDispatchOrder(frm)" in source
    assert "renderReadyDispatchPlan(frm);" in source
    assert "almadina-dispatch-plan-summary" in source
    assert "خطة الإرسال الحالية" in source


def test_ready_plan_fetch_and_actions_follow_server_intake_owner_boundary() -> None:
    source = UX.read_text(encoding="utf-8")

    assert "function isIntakeOwnerOrAdmin(frm)" in source
    assert 'actor === "Administrator"' in source
    assert "actor === assignee" in source
    assert "function canUseReadyDispatchPlan(frm)" in source
    assert "isIntakeOwnerOrAdmin(frm) && (canEditOrder(frm) || canDispatchOrder(frm))" in source

    render_start = source.index("function renderReadyDispatchPlan(frm)")
    render_end = source.index("function workerOptions", render_start)
    render_block = source[render_start:render_end]
    assert "!canUseReadyDispatchPlan(frm)" in render_block

    reconcile_start = source.index("function reconcileIntakeActions(frm)")
    reconcile_block = source[reconcile_start:]
    assert "isIntakeOwnerOrAdmin(frm) && canEditOrder(frm)" in reconcile_block
    assert "isIntakeOwnerOrAdmin(frm) && canDispatchOrder(frm)" in reconcile_block


def test_dispatch_confirmation_is_read_only_and_uses_persisted_server_plan() -> None:
    source = UX.read_text(encoding="utf-8")

    assert "planned_dispatch_service.get_planned_dispatch_context" in source
    assert 'title: __("تأكيد الإرسال للإنتاج")' in source
    assert '{ fieldname: "plan", fieldtype: "HTML" }' in source
    assert 'primary_action_label: __("تأكيد الإرسال للإنتاج")' in source
    block_start = source.index("function openDispatchConfirmation(frm)")
    block_end = source.index("function reconcileIntakeActions(frm)", block_start)
    block = source[block_start:block_end]
    assert 'fieldtype: "Select"' not in block


def test_real_dispatch_mutation_sends_only_order_identity() -> None:
    source = UX.read_text(encoding="utf-8")
    block = _dispatch_call_block(source)

    assert "args: { order_name: frm.doc.name }" in block
    assert "route_name" not in block
    assert "assignee" not in block
    assert "path:" not in block


def test_dispatch_frontend_is_lifecycle_safe_on_slow_navigation_and_errors() -> None:
    source = UX.read_text(encoding="utf-8")

    assert "window.AlmdinaDocumentContext" in source
    assert "const optionsToken = captureDocumentContext(frm);" in source
    assert "const mutationToken = captureDocumentContext(frm);" in source
    assert "if (!isCurrentDocumentContext(frm, mutationToken)) return;" in source
    assert "dialog.disable_primary_action();" in source
    assert "dialog.enable_primary_action();" in source
    assert "let dispatching = false;" in source
    assert "if (dispatching || !isCurrentDocumentContext(frm, optionsToken))" in source
    assert "setTimeout(" not in source


def test_dirty_form_is_never_silently_overwritten_by_dispatch() -> None:
    source = UX.read_text(encoding="utf-8")

    assert 'typeof frm.is_dirty === "function" && frm.is_dirty()' in source
    assert "Boolean(frm.doc.__unsaved)" in source
    assert "if (!requirePersistedFormState(frm)) return null;" in source
    assert "if (!requirePersistedFormState(frm)) return;" in source
    assert "if (hasUnsavedChanges(frm))" in source


def test_service_exposes_narrow_server_authoritative_contract() -> None:
    source = SERVICE.read_text(encoding="utf-8")

    assert "def dispatch_planned_order(order_name: str)" in source
    assert "route_name" not in source
    assert "assignee" not in source
    assert "PlannedDispatchPermissionDenied" in source
    assert "frappe.PermissionError" in source


def test_application_owns_lock_state_authorization_and_atomic_mutation_order() -> None:
    source = APPLICATION.read_text(encoding="utf-8")

    lock = source.index("repository.lock_order(order_name)")
    reread = source.index("repository.get_planned_dispatch_order(order_name)", lock)
    create = source.index("repository.create_stage(", reread)
    activate = source.index("repository.activate_planned_dispatch(", create)
    event = source.index("repository.log_stage_event(", activate)
    assert lock < reread < create < activate < event
    assert "Capability.DISPATCH_ORDER" in source
    assert "decide_production_action" in source
    assert "route.first_stage" in source
    assert "cancel_active_order_stages" not in source
    assert "frappe.db.commit" not in source
    assert "import frappe" not in source


def test_contradictory_active_stage_fails_closed() -> None:
    source = APPLICATION.read_text(encoding="utf-8")
    stage_source = STAGES.read_text(encoding="utf-8")

    assert source.count("repository.has_active_order_stage(order.name)") >= 2
    assert "يوجد سجل إنتاج نشط غير متوافق مع حالة الطلب" in source
    assert "def has_active_order_stage(order_name: str) -> bool:" in stage_source
    assert "piece_label" in stage_source


def test_successful_activation_clears_only_intake_marker_in_same_tracking_write() -> None:
    source = TRACKING.read_text(encoding="utf-8")

    assert "clear_workflow_stage: bool = False" in source
    assert 'values["workflow_stage"] = None' in source
    assert "frappe.db.commit" not in source
