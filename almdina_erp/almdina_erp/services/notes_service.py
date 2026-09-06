from __future__ import annotations

from typing import Any

import frappe
from frappe import _

from almdina_erp.almdina_erp.application.notes.contracts import (
    CUSTOMER_DOCTYPE,
    ORDER_DOCTYPE,
    NotesValidationError,
    normalize_note_content,
    normalize_reference,
    normalize_request_id,
    plain_text_preview,
    request_subject,
)
from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe.authorization_gateway import (
    document_has_capability,
    require_document_capability,
)
from almdina_erp.almdina_erp.infrastructure.frappe.notes_repository import (
    FrappeNotesRepository,
)


_repository = FrappeNotesRepository()


def _validation_error(error: NotesValidationError) -> None:
    frappe.throw(_(str(error)))


def _normalize_reference(reference_doctype: object, reference_name: object) -> tuple[str, str]:
    try:
        return normalize_reference(reference_doctype, reference_name)
    except NotesValidationError as error:
        _validation_error(error)
    raise AssertionError("frappe.throw must interrupt execution")


def _normalize_content(content: object) -> str:
    try:
        return normalize_note_content(content)
    except NotesValidationError as error:
        _validation_error(error)
    raise AssertionError("frappe.throw must interrupt execution")


def _normalize_request(request_id: object) -> str:
    try:
        return normalize_request_id(request_id)
    except NotesValidationError as error:
        _validation_error(error)
    raise AssertionError("frappe.throw must interrupt execution")


def _authorized_order(order_name: object) -> Any:
    resolved = str(order_name or "").strip()
    if not resolved:
        frappe.throw(_("A Door Cutting Order is required."))
    order = frappe.get_doc(ORDER_DOCTYPE, resolved)
    # Native DCO permission hooks contain the current worker/assigned-order scope.
    # Reading notes follows concrete DCO visibility and is deliberately independent
    # from EDIT_ORDER and the DCO lifecycle.
    order.check_permission("read")
    return order


def _can_add_note(order: Any) -> bool:
    return document_has_capability(
        order,
        Capability.ADD_INTERNAL_NOTE,
        user=frappe.session.user,
    )


def _can_manage_important(order: Any) -> bool:
    return document_has_capability(
        order,
        Capability.MANAGE_IMPORTANT_NOTE,
        user=frappe.session.user,
    )


def _require_add_note(order: Any) -> None:
    require_document_capability(
        order,
        Capability.ADD_INTERNAL_NOTE,
        user=frappe.session.user,
        message=_("لا تملك صلاحية إضافة ملاحظة داخلية على هذا الطلب."),
    )


def _require_manage_important(order: Any) -> None:
    require_document_capability(
        order,
        Capability.MANAGE_IMPORTANT_NOTE,
        user=frappe.session.user,
        message=_("لا تملك صلاحية تعيين الملاحظة المهمة لهذا الطلب."),
    )


def _customer_has_read_access(customer: Any) -> bool:
    return bool(
        frappe.has_permission(
            CUSTOMER_DOCTYPE,
            ptype="read",
            doc=customer,
            user=frappe.session.user,
        )
    )


def _linked_customer(order: Any, customer_name: object, *, required: bool) -> Any | None:
    resolved = str(customer_name or "").strip()
    linked = str(order.get("customer") or "").strip()
    if not resolved or not linked or resolved != linked:
        if required:
            frappe.throw(
                _("Customer notes are only available for the customer linked to this order."),
                frappe.PermissionError,
            )
        return None

    customer = frappe.get_doc(CUSTOMER_DOCTYPE, resolved)
    if _customer_has_read_access(customer):
        return customer
    if required:
        frappe.throw(
            _("You do not have permission to access notes for this customer."),
            frappe.PermissionError,
        )
    return None


def _authorize_reference(
    reference_doctype: object,
    reference_name: object,
    *,
    order_name: object | None = None,
) -> tuple[str, str, Any]:
    doctype, name = _normalize_reference(reference_doctype, reference_name)
    if doctype == ORDER_DOCTYPE:
        order = _authorized_order(name)
        context_order = str(order_name or "").strip()
        if context_order and context_order != order.name:
            frappe.throw(_("The note reference does not match the requested order."))
        return doctype, name, order

    # Customer notes are intentionally contextual: DCO visibility by itself does
    # not grant arbitrary Customer access. The caller must prove both access to a
    # concrete DCO and that this Customer is the one linked by that DCO.
    order = _authorized_order(order_name)
    _linked_customer(order, name, required=True)
    return doctype, name, order


def _valid_important_row(order_name: str, comment_name: str) -> dict[str, Any] | None:
    if not comment_name:
        return None
    row = _repository.get_note(comment_name)
    if not row:
        return None
    if str(row.get("comment_type") or "") != "Comment":
        return None
    if str(row.get("reference_doctype") or "") != ORDER_DOCTYPE:
        return None
    if str(row.get("reference_name") or "") != order_name:
        return None
    return row


def _order_notes_payload(order: Any) -> dict[str, Any]:
    projection = _repository.order_projection(order.name)
    important_name = projection["comment"]
    important_row = _valid_important_row(order.name, important_name)
    effective_important = important_name if important_row else ""
    order_notes = _repository.list_notes(
        ORDER_DOCTYPE,
        order.name,
        important_comment=effective_important,
    )
    important_note = (
        _repository.serialize_note(
            important_row,
            important_comment=effective_important,
        )
        if important_row
        else None
    )
    preview = (
        plain_text_preview(_repository.plain_text(important_row))
        if important_row
        else ""
    )
    return {
        "notes": order_notes,
        "count": len(order_notes),
        "important_note": important_note,
        "important_note_comment": effective_important,
        "important_note_preview": preview,
    }


def _customer_notes_payload(order: Any) -> dict[str, Any]:
    customer_name = str(order.get("customer") or "").strip()
    if not customer_name:
        return {
            "customer": "",
            "available": False,
            "notes": [],
            "count": 0,
        }
    customer = _linked_customer(order, customer_name, required=False)
    if not customer:
        return {
            "customer": customer_name,
            "available": False,
            "notes": [],
            "count": 0,
        }
    notes = _repository.list_notes(CUSTOMER_DOCTYPE, customer_name)
    return {
        "customer": customer_name,
        "available": True,
        "notes": notes,
        "count": len(notes),
    }


def _context(order: Any) -> dict[str, Any]:
    order_payload = _order_notes_payload(order)
    customer_payload = _customer_notes_payload(order)
    customer_access = bool(customer_payload["available"])
    can_add = _can_add_note(order)
    can_manage_important = _can_manage_important(order)
    return {
        "order": str(order.name),
        "customer": customer_payload["customer"],
        "order_notes": order_payload["notes"],
        "customer_notes": customer_payload["notes"],
        "counts": {
            "order": order_payload["count"],
            "customer": customer_payload["count"],
        },
        "important_note": order_payload["important_note"],
        "important_note_comment": order_payload["important_note_comment"],
        "important_note_preview": order_payload["important_note_preview"],
        "permissions": {
            "can_add_order_note": can_add,
            "can_manage_important_note": can_manage_important,
            "can_view_customer_notes": customer_access,
            # Customer collaboration is permitted only through the linked DCO
            # context and the same explicit add-note capability. It never grants
            # arbitrary Customer write authority.
            "can_add_customer_note": customer_access and can_add,
        },
    }


@frappe.whitelist()
def get_order_notes_context(order_name: str) -> dict[str, Any]:
    return _context(_authorized_order(order_name))


@frappe.whitelist()
def get_notes(
    reference_doctype: str,
    reference_name: str,
    order_name: str | None = None,
) -> dict[str, Any]:
    doctype, name, order = _authorize_reference(
        reference_doctype,
        reference_name,
        order_name=order_name,
    )
    if doctype == ORDER_DOCTYPE:
        payload = _order_notes_payload(order)
        return {
            "reference_doctype": doctype,
            "reference_name": name,
            **payload,
        }
    notes = _repository.list_notes(doctype, name)
    return {
        "reference_doctype": doctype,
        "reference_name": name,
        "notes": notes,
        "count": len(notes),
        "important_note": None,
        "important_note_comment": "",
        "important_note_preview": "",
    }


@frappe.whitelist()
def add_note(
    reference_doctype: str,
    reference_name: str,
    content: str,
    request_id: str,
    order_name: str | None = None,
    important: int | bool = False,
) -> dict[str, Any]:
    doctype, name, order = _authorize_reference(
        reference_doctype,
        reference_name,
        order_name=order_name,
    )
    _require_add_note(order)
    normalized_content = _normalize_content(content)
    normalized_request = _normalize_request(request_id)
    mark_important = bool(int(important)) if isinstance(important, (str, int)) else bool(important)
    if mark_important and doctype != ORDER_DOCTYPE:
        frappe.throw(_("Only Door Cutting Order notes can be marked as important."))
    if mark_important:
        _require_manage_important(order)

    # Serialize same-reference note creation. Together with the namespaced native
    # Comment.subject operation key this makes a lost-response retry idempotent.
    _repository.lock_reference(doctype, name)
    subject = request_subject(normalized_request)
    existing = _repository.find_by_request_subject(doctype, name, subject)
    if existing:
        if str(existing.get("content") or "").strip() != normalized_content:
            frappe.throw(_("This note request was already used with different content."))
        comment = existing
    else:
        comment = _repository.create_note(
            reference_doctype=doctype,
            reference_name=name,
            content=normalized_content,
            subject=subject,
            user=frappe.session.user,
        )

    if mark_important:
        preview = plain_text_preview(_repository.plain_text(comment))
        _repository.set_order_projection(
            order.name,
            comment_name=str(comment.get("name") or ""),
            preview=preview,
        )
    return _context(order)


@frappe.whitelist()
def set_important_note(order_name: str, comment_name: str) -> dict[str, Any]:
    order = _authorized_order(order_name)
    _require_manage_important(order)
    resolved_comment = str(comment_name or "").strip()
    if not resolved_comment:
        frappe.throw(_("Select a note to mark as important."))

    _repository.lock_reference(ORDER_DOCTYPE, order.name)
    comment = _valid_important_row(order.name, resolved_comment)
    if not comment:
        frappe.throw(
            _("The selected Comment is not a valid note for this order."),
            frappe.PermissionError,
        )
    preview = plain_text_preview(_repository.plain_text(comment))
    if not preview:
        frappe.throw(_("An empty Comment cannot be marked as important."))
    _repository.set_order_projection(
        order.name,
        comment_name=resolved_comment,
        preview=preview,
    )
    return _context(order)


@frappe.whitelist()
def clear_important_note(order_name: str) -> dict[str, Any]:
    order = _authorized_order(order_name)
    _require_manage_important(order)
    _repository.lock_reference(ORDER_DOCTYPE, order.name)
    _repository.set_order_projection(
        order.name,
        comment_name=None,
        preview=None,
    )
    return _context(order)


__all__ = [
    "add_note",
    "clear_important_note",
    "get_notes",
    "get_order_notes_context",
    "set_important_note",
]
