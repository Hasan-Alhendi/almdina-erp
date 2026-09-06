from __future__ import annotations

import json
from pathlib import Path

import pytest

from almdina_erp.almdina_erp.application.notes.contracts import (
    NOTE_MAX_LENGTH,
    NotesValidationError,
    is_collaborative_note_subject,
    normalize_note_content,
    normalize_reference,
    normalize_request_id,
    plain_text_preview,
    request_subject,
)
from almdina_erp.almdina_erp.application.security.permission_matrix import (
    CAPABILITY_PRESENTATION,
    normalize_capability_state,
)
from almdina_erp.almdina_erp.domain.security.authorization import (
    CAPABILITY_CATALOG,
    Capability,
)


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "almdina_erp"
CONTRACTS = APP / "application" / "notes" / "contracts.py"
REPOSITORY = APP / "infrastructure" / "frappe" / "notes_repository.py"
SERVICE = APP / "services" / "notes_service.py"
PROJECTION = APP / "services" / "notes_projection_service.py"
DOCTYPE = APP / "doctype" / "door_cutting_order" / "door_cutting_order.json"
HOOKS = ROOT / "hooks.py"
MANIFEST = ROOT / "frontend_assets.py"
PANEL = ROOT / "public" / "js" / "notes" / "notes_panel.js"
LIST_INTEGRATION = ROOT / "public" / "js" / "notes" / "notes_dco_list_integration.js"
FORM_INTEGRATION = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "notes"
    / "door_cutting_order_notes_ux.js"
)
CSS = ROOT / "public" / "css" / "notes.css"


def source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def dco_meta() -> dict:
    return json.loads(source(DOCTYPE))


def field(meta: dict, fieldname: str) -> dict:
    return next(row for row in meta["fields"] if row.get("fieldname") == fieldname)


def test_a156_note_contracts_are_small_bounded_and_reference_scoped() -> None:
    assert normalize_reference("Door Cutting Order", "DCO-2026-00001") == (
        "Door Cutting Order",
        "DCO-2026-00001",
    )
    assert normalize_reference("Customer", "CUST-0001") == ("Customer", "CUST-0001")
    with pytest.raises(NotesValidationError):
        normalize_reference("Sales Invoice", "SINV-1")
    with pytest.raises(NotesValidationError):
        normalize_note_content("   ")
    with pytest.raises(NotesValidationError):
        normalize_note_content("x" * (NOTE_MAX_LENGTH + 1))
    assert normalize_note_content("  ملاحظة قصيرة  ") == "ملاحظة قصيرة"


def test_a156_request_id_and_preview_support_retryable_weak_network_flow() -> None:
    request_id = "47a7b77f-0790-469a-a643-c12e276e6d03"
    assert normalize_request_id(request_id) == request_id
    assert request_subject(request_id) == f"almdina-note:{request_id}"
    with pytest.raises(NotesValidationError):
        normalize_request_id("short")

    preview = plain_text_preview("  لا   يتم\nالتسليم قبل الدفع  ", limit=18)
    assert "\n" not in preview
    assert len(preview) <= 18
    assert preview.endswith("…")


def test_a156_collaborative_comments_have_an_explicit_native_namespace() -> None:
    request_id = "47a7b77f-0790-469a-a643-c12e276e6d03"
    subject = request_subject(request_id)
    assert is_collaborative_note_subject(subject) is True
    assert is_collaborative_note_subject("Order imported") is False
    assert is_collaborative_note_subject("") is False

    repository = source(REPOSITORY)
    assert "NOTE_SUBJECT_PREFIX" in repository
    assert '"subject": ["like", f"{NOTE_SUBJECT_PREFIX}%"]' in repository
    assert "is_collaborative_note_subject(row.get(\"subject\"))" in repository


def test_a156_collaboration_actions_are_explicit_assignable_capabilities() -> None:
    add_definition = CAPABILITY_CATALOG[Capability.ADD_INTERNAL_NOTE]
    important_definition = CAPABILITY_CATALOG[Capability.MANAGE_IMPORTANT_NOTE]

    assert Capability.ADD_INTERNAL_NOTE == "add_internal_note"
    assert Capability.MANAGE_IMPORTANT_NOTE == "manage_important_note"
    assert add_definition.applies_to == "Door Cutting Order"
    assert important_definition.applies_to == "Door Cutting Order"
    assert add_definition.category == "order"
    assert important_definition.category == "order"
    assert add_definition.custom is True
    assert important_definition.custom is True

    assert CAPABILITY_PRESENTATION[Capability.ADD_INTERNAL_NOTE]["label"] == "إضافة ملاحظة داخلية"
    assert CAPABILITY_PRESENTATION[Capability.MANAGE_IMPORTANT_NOTE]["label"] == "تعيين الملاحظة المهمة"
    assert CAPABILITY_PRESENTATION[Capability.MANAGE_IMPORTANT_NOTE]["risk"] == "sensitive"

    normalized = normalize_capability_state({Capability.ADD_INTERNAL_NOTE: True})
    assert normalized[Capability.ADD_INTERNAL_NOTE] is True
    assert normalized[Capability.VIEW_ORDERS] is True
    assert normalized[Capability.EDIT_ORDER] is False


def test_a156_uses_native_comment_as_only_note_store_and_filters_system_events() -> None:
    repository = source(REPOSITORY)
    assert '"doctype": "Comment"' in repository
    assert '"comment_type": "Comment"' in repository
    assert '"reference_doctype": reference_doctype' in repository
    assert '"reference_name": reference_name' in repository
    assert '"subject": subject' in repository
    assert "Order Note" not in repository


def test_a156_server_authorization_is_document_scoped_and_customer_is_linked() -> None:
    service = source(SERVICE)
    assert 'order.check_permission("read")' in service
    assert "document_has_capability(" in service
    assert "require_document_capability(" in service
    assert "Capability.ADD_INTERNAL_NOTE" in service
    assert "Capability.MANAGE_IMPORTANT_NOTE" in service
    assert 'resolved != linked' in service
    assert '_customer_has_read_access(customer)' in service
    assert 'frappe.PermissionError' in service
    assert '"can_add_order_note": can_add' in service
    assert '"can_manage_important_note": can_manage_important' in service
    assert '"can_add_customer_note": customer_access and can_add' in service
    assert '"can_add_order_note": True' not in service
    assert '"can_manage_important_note": True' not in service
    assert 'EDIT_ORDER' not in service
    assert 'frm.save' not in service


def test_a156_mutations_require_separate_add_and_important_authority() -> None:
    service = source(SERVICE)
    add_body = service.split("def add_note(", 1)[1].split("def set_important_note", 1)[0]
    set_body = service.split("def set_important_note", 1)[1].split("def clear_important_note", 1)[0]
    clear_body = service.split("def clear_important_note", 1)[1]

    assert "_require_add_note(order)" in add_body
    assert "if mark_important:" in add_body
    assert "_require_manage_important(order)" in add_body
    assert "_require_manage_important(order)" in set_body
    assert "_require_manage_important(order)" in clear_body


def test_a156_lost_response_retry_is_server_idempotent() -> None:
    repository = source(REPOSITORY)
    service = source(SERVICE)
    assert "for update" in repository.lower()
    assert "find_by_request_subject" in repository
    assert "request_subject(normalized_request)" in service
    assert "find_by_request_subject(doctype, name, subject)" in service
    assert "already used with different content" in service


def test_a156_projection_is_list_only_and_never_updates_dco_modified() -> None:
    repository = source(REPOSITORY)
    projection = source(PROJECTION)
    hooks = source(HOOKS)
    assert '"important_note_comment"' in repository
    assert '"important_note_preview"' in repository
    assert "update_modified=False" in repository
    assert "preserve_order_projection_on_save" in projection
    assert "refresh_important_projection_from_comment" in projection
    assert "clear_important_projection_for_deleted_comment" in projection
    assert "notes_projection_service.preserve_order_projection_on_save" in hooks
    assert "notes_projection_service.refresh_important_projection_from_comment" in hooks
    assert "notes_projection_service.clear_important_projection_for_deleted_comment" in hooks


def test_a156_dco_metadata_keeps_official_order_notes_separate_from_projection() -> None:
    meta = dco_meta()
    official = field(meta, "order_notes")
    preview = field(meta, "important_note_preview")
    pointer = field(meta, "important_note_comment")

    assert official["fieldtype"] == "Small Text"
    assert official["in_list_view"] == 1
    assert "read_only" not in official

    assert preview["fieldtype"] == "Small Text"
    assert preview["hidden"] == 1
    assert preview["in_list_view"] == 1
    assert preview["read_only"] == 1
    assert preview["no_copy"] == 1
    assert preview["label"] == "ملاحظة مهمة"

    assert pointer["fieldtype"] == "Link"
    assert pointer["options"] == "Comment"
    assert pointer["hidden"] == 1
    assert pointer["read_only"] == 1

    order = meta["field_order"]
    assert order.index("important_note_preview") == order.index("order_notes") + 1
    assert order.index("important_note_comment") == order.index("important_note_preview") + 1


def test_a156_notes_panel_is_reusable_rtl_and_independent_from_form_save() -> None:
    panel = source(PANEL)
    manifest = source(MANIFEST)
    css = source(CSS)

    assert '"/assets/almdina_erp/js/notes/notes_panel.js"' in manifest
    assert '"/assets/almdina_erp/css/notes.css"' in manifest
    assert 'const MAX_LENGTH = 500' in panel
    assert 'data-notes-tab="order"' in panel
    assert 'data-notes-tab="customer"' in panel
    assert "تعيين كملاحظة مهمة" in panel
    assert "الملاحظة المهمة الحالية" in panel
    assert 'dir="rtl"' in panel
    assert "state.pendingRequest" in panel
    assert "requestIdFor(key)" in panel
    assert "state.error = errorMessage(error)" in panel
    assert "frm.save(" not in panel
    assert "frm.set_value" not in panel
    assert "frm.dirty" not in panel
    assert ".almdina-notes-panel" in css
    assert "@media (max-width: 600px)" in css
    assert "@media (prefers-reduced-motion: reduce)" in css
    assert ":focus-visible" in css


def test_a156_dco_form_adapter_never_enters_document_save_lifecycle() -> None:
    form = source(FORM_INTEGRATION)
    manifest = source(MANIFEST)
    assert "door_cutting_order_notes_ux.js" in manifest
    assert "AlmdinaNotesPanel" in form
    assert "add_custom_button" in form
    assert "important_note_preview" in form
    assert "frm.save(" not in form
    assert "frm.set_value" not in form
    assert "frm.dirty" not in form


def test_a156_desktop_list_uses_projection_without_comment_n_plus_one() -> None:
    integration = source(LIST_INTEGRATION)
    manifest = source(MANIFEST)
    assert '"/assets/almdina_erp/js/notes/notes_dco_list_integration.js"' in manifest
    assert 'const IMPORTANT_FIELD = "important_note_preview"' in integration
    assert "dco-important-note-link" in integration
    assert "reorderImportantColumn" in integration
    assert "AlmdinaNotesPanel" in integration
    assert "frappe.call" not in integration
    assert '"Comment"' not in integration


def test_a156_important_note_is_rendered_inside_custom_mobile_card() -> None:
    integration = source(LIST_INTEGRATION)
    css = source(CSS)
    assert "reconcileMobileCards" in integration
    assert 'card.querySelector(".dco-mobile-order-card")' in integration
    assert 'className = "dco-card-important-note"' in integration
    assert 'card.insertBefore(next, date)' in integration
    assert "if (!preview)" in integration
    assert "existing.remove()" in integration
    assert ".dco-card-important-note" in css
    assert "-webkit-line-clamp: 2" in css


def test_a156_context_update_reuses_same_projection_for_form_desktop_and_mobile() -> None:
    panel = source(PANEL)
    form = source(FORM_INTEGRATION)
    integration = source(LIST_INTEGRATION)
    assert 'const NOTE_UPDATED_EVENT = "almdina:notes-context-updated"' in panel
    assert 'const UPDATED_EVENT = "almdina:notes-context-updated"' in form
    assert 'const UPDATED_EVENT = "almdina:notes-context-updated"' in integration
    assert "important_note_preview" in panel
    assert "important_note_preview" in form
    assert "important_note_preview" in integration
