from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "almdina_erp"
REPOSITORY = APP / "infrastructure" / "frappe" / "notes_repository.py"
SERVICE = APP / "services" / "notes_service.py"
PANEL = ROOT / "public" / "js" / "notes" / "notes_panel.js"
CSS = ROOT / "public" / "css" / "notes_interactions.css"
MANIFEST = ROOT / "frontend_assets.py"
ENDPOINTS = ROOT / "tests" / "security_endpoint_contracts.py"


def source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_note_mutations_keep_native_comment_as_canonical_store() -> None:
    repository = source(REPOSITORY)
    assert 'document = frappe.get_doc("Comment", comment_name)' in repository
    assert "document.save(ignore_permissions=True)" in repository
    assert 'frappe.delete_doc("Comment", comment_name, ignore_permissions=True)' in repository
    assert '"modified"' in repository
    assert '"is_edited"' in repository
    assert "Order Note" not in repository


def test_note_edit_delete_are_owner_scoped_server_actions() -> None:
    service = source(SERVICE)
    assert "def _note_for_reference(" in service
    assert "def _require_note_mutation(" in service
    assert "def _is_owned_note(" in service
    assert "frappe.session.user" in service
    assert "يمكنك تعديل أو حذف الملاحظات التي أضفتها أنت فقط" in service
    assert "_require_add_note(order)" in service

    edit_body = service.split("def edit_note(", 1)[1].split("def delete_note(", 1)[0]
    delete_body = service.split("def delete_note(", 1)[1].split("def set_important_note", 1)[0]
    for body in (edit_body, delete_body):
        assert "_authorize_reference(" in body
        assert "_repository.lock_reference(doctype, name)" in body
        assert "_require_note_mutation(order, comment)" in body
        assert "return _context(order)" in body
    assert "_note_for_reference(doctype, name, comment_name)" in edit_body
    assert "_note_for_reference(doctype, name, resolved_comment)" in delete_body
    assert "_repository.update_note(" in edit_body
    assert "_repository.delete_note(" in delete_body


def test_edit_delete_use_optimistic_concurrency_and_retry_safe_semantics() -> None:
    service = source(SERVICE)
    panel = source(PANEL)
    assert "def _require_fresh_note(" in service
    assert "frappe.TimestampMismatchError" in service
    assert "تم تغيير هذه الملاحظة في جلسة أخرى" in service
    assert "desired_content=normalized_content" in service
    assert 'if not frappe.db.exists("Comment", resolved_comment)' in service
    assert "expected_modified: str" in service
    assert 'expected_modified: note.modified || ""' in panel
    assert panel.count('expected_modified: note.modified || ""') == 2


def test_important_note_cannot_be_changed_without_important_authority() -> None:
    service = source(SERVICE)
    mutation_guard = service.split("def _require_note_mutation", 1)[1].split(
        "def _note_actions",
        1,
    )[0]
    action_projection = service.split("def _note_actions", 1)[1].split(
        "def _decorate_note",
        1,
    )[0]
    assert "_is_current_important(order, row.get(\"name\"))" in mutation_guard
    assert "_require_manage_important(order)" in mutation_guard
    assert 'note.get("is_important") is True' in action_projection
    assert "not _can_manage_important(order)" in action_projection


def test_note_action_visibility_is_server_driven_not_role_driven() -> None:
    service = source(SERVICE)
    panel = source(PANEL)
    assert '"can_edit": can_mutate' in service
    assert '"can_delete": can_mutate' in service
    assert "note.can_edit === true" in panel
    assert "note.can_delete === true" in panel
    assert "frappe.user_roles" not in panel
    assert "has_role" not in panel


def test_panel_has_inline_edit_and_confirmed_delete_without_dco_save() -> None:
    panel = source(PANEL)
    assert "notes_service.edit_note" in panel
    assert "notes_service.delete_note" in panel
    assert 'data-notes-action="edit"' in panel
    assert 'data-notes-action="delete"' in panel
    assert 'data-notes-action="save-edit"' in panel
    assert 'data-notes-action="cancel-edit"' in panel
    assert 'data-notes-input="edit-content"' in panel
    assert "حفظ التعديل" in panel
    assert "هل تريد حذف هذه الملاحظة؟ لا يمكن التراجع عن الحذف." in panel
    assert "frappe.confirm" in panel
    assert "frm.save(" not in panel
    assert "frm.set_value" not in panel
    assert "frm.dirty" not in panel


def test_edit_lifecycle_is_scoped_and_escape_cancels_before_closing() -> None:
    panel = source(PANEL)
    assert 'editingComment: ""' in panel
    assert 'editDraft: ""' in panel
    assert "function clearEditState()" in panel
    assert "if (clearEdit) clearEditState()" in panel
    assert "if (state.editingComment && !state.mutating)" in panel
    assert "cancelEdit();" in panel
    assert 'frappe.router.on("change"' in panel
    assert "if (state.isOpen) close();" in panel


def test_editing_or_deleting_important_note_reuses_existing_projection_event() -> None:
    panel = source(PANEL)
    service = source(SERVICE)
    assert 'const NOTE_UPDATED_EVENT = "almdina:notes-context-updated"' in panel
    assert "emitContextUpdated(context)" in panel
    assert "important_note_preview" in panel
    assert "_repository.update_note(" in service
    assert "_repository.delete_note(" in service
    # Native Comment on_update/on_trash hooks remain the projection owner.
    hooks = source(ROOT / "hooks.py")
    assert "refresh_important_projection_from_comment" in hooks
    assert "clear_important_projection_for_deleted_comment" in hooks


def test_edit_delete_styles_are_static_responsive_and_focus_visible() -> None:
    manifest = source(MANIFEST)
    css = source(CSS)
    assert '"/assets/almdina_erp/css/notes_interactions.css"' in manifest
    assert ".almdina-note-actions" in css
    assert ".almdina-note-editor" in css
    assert ".almdina-note-action.is-danger" in css
    assert ":focus-visible" in css
    assert "@media (max-width: 600px)" in css


def test_whitelisted_edit_delete_endpoints_have_security_contracts() -> None:
    endpoints = source(ENDPOINTS)
    notes_group = endpoints.split(
        '"almdina_erp.almdina_erp.services.notes_service"',
        1,
    )[1].split("),", 1)[0]
    assert '"edit_note"' in notes_group
    assert '"delete_note"' in notes_group
