from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "almdina_erp"
REPOSITORY = APP / "infrastructure" / "frappe" / "notes_repository.py"
DCO_NOTES_UX = ROOT / "public" / "js" / "door_cutting_order" / "notes" / "door_cutting_order_notes_ux.js"
DOCUMENT_CONTEXT = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "core"
    / "door_cutting_order_document_context.js"
)


def source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_note_action_identity_uses_canonical_frappe_owner() -> None:
    repository = source(REPOSITORY)
    assert '"author_user": str(note.get("owner") or note.get("comment_email") or "").strip()' in repository
    assert 'note["comment_email"] = str(note.get("owner") or "").strip()' in repository
    assert "Frappe `owner` is the stable authenticated user identity" in repository


def test_toolbar_count_is_refreshed_for_each_order_identity() -> None:
    ux = source(DCO_NOTES_UX)
    assert "function orderIdentity(frm)" in ux
    assert "function resetIdentityState(frm, identity)" in ux
    assert "function refreshNotesSummary(frm)" in ux
    assert "_almdinaNotesOrderIdentity" in ux
    assert "_almdinaNotesSummaryGeneration" in ux
    assert "get_order_notes_context" in ux
    assert "Never paint the previous order's count" in ux


def test_toolbar_summary_is_stale_response_safe_and_dco_save_free() -> None:
    ux = source(DCO_NOTES_UX)
    assert "function isCurrentSummaryRequest(frm, identity, generation)" in ux
    assert "applyContextSnapshot(frm, context, identity, generation)" in ux
    assert "String(context.order || \"\") !== String(identity || \"\")" in ux
    assert "frm._almdinaNotesSummaryGeneration = Number(frm._almdinaNotesSummaryGeneration || 0) + 1" in ux
    assert "frm.save(" not in ux
    assert "frm.set_value" not in ux
    assert "frm.dirty" not in ux


def test_notes_toolbar_registration_uses_stable_frappe_action_identity() -> None:
    ux = source(DCO_NOTES_UX)
    ensure_body = ux.split("function ensureNotesButton(frm)", 1)[1].split(
        "function notesSurfaceReady(frm)",
        1,
    )[0]

    assert 'const NOTES_ACTION_LABEL = __("الملاحظات");' in ux
    assert "frm.add_custom_button(NOTES_ACTION_LABEL" in ensure_body
    assert "frm.add_custom_button(buttonLabel(frm)" not in ux
    assert "Frappe indexes custom actions by the label" in ensure_body
    assert "clearStaleButtonRegistration(frm);" in ensure_body


def test_notes_toolbar_visibility_is_saved_document_not_draft_or_assignment_scoped() -> None:
    ux = source(DCO_NOTES_UX)
    saved_body = ux.split("function isSavedOrder(frm)", 1)[1].split(
        "function orderIdentity(frm)",
        1,
    )[0]
    ensure_body = ux.split("function ensureNotesButton(frm)", 1)[1].split(
        "function notesSurfaceReady(frm)",
        1,
    )[0]

    for forbidden in (
        "Draft",
        "status",
        "current_assignee",
        "current_department",
        "production_path",
        "edit_order",
    ):
        assert forbidden not in saved_body
        assert forbidden not in ensure_body

    assert "isSavedOrder(frm)" in ensure_body
    assert "removeNotesButton(frm);" in ensure_body


def test_notes_toolbar_is_a_central_dco_recoverable_surface_without_new_observer() -> None:
    ux = source(DCO_NOTES_UX)
    assert 'const NOTES_SURFACE = "collaborative-notes-toolbar";' in ux
    assert "function notesSurfaceReady(frm)" in ux
    assert "function recoverNotesSurface(frm)" in ux
    assert "context.registerSurface(NOTES_SURFACE" in ux
    assert "isReady: notesSurfaceReady" in ux
    assert "recover: recoverNotesSurface" in ux
    assert "registerNotesSurface();" in ux
    assert "MutationObserver" not in ux


def test_stage_and_form_lifecycle_schedule_registered_surface_recovery() -> None:
    context = source(DOCUMENT_CONTEXT)
    stage_ready_body = context.split("function notifyStageContextReady(frm)", 1)[1].split(
        "function ensureStageContext(frm, options = {})",
        1,
    )[0]
    hooks_body = context.split('frappe.ui.form.on("Door Cutting Order"', 1)[1]

    assert "scheduleSettle(frm, 0);" in stage_ready_body
    assert "refresh(frm)" in hooks_body
    assert "onload_post_render(frm)" in hooks_body
    assert "after_save(frm)" in hooks_body
    assert hooks_body.count("scheduleSettle(frm, 0);") >= 3


def test_notes_form_hook_reconciles_after_render_and_keeps_new_orders_clean() -> None:
    ux = source(DCO_NOTES_UX)
    hooks_body = ux.split("frappe.ui.form.on(DOCTYPE", 1)[1].split(
        "window.AlmdinaDoorCuttingOrderNotesUX",
        1,
    )[0]

    assert "onload_post_render(frm)" in hooks_body
    assert "ensureNotesButton(frm);" in hooks_body
    assert "resetIdentityState(frm, \"\");" in hooks_body
    assert "removeNotesButton(frm);" in hooks_body
