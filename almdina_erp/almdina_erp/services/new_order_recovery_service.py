from __future__ import annotations

from typing import Any
from uuid import UUID

import frappe
from frappe import _

from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe.authorization_gateway import (
    require_doctype_capability,
)


_DCO_DOCTYPE = "Door Cutting Order"
_TOKEN_FIELD = "recovery_creation_token"
_USER_FIELD = "recovery_creation_user"


def _creation_token(value: Any, *, required: bool) -> str | None:
    candidate = str(value or "").strip()
    if not candidate:
        if required:
            frappe.throw(_("هوية إنشاء مسودة الطلب مطلوبة."), frappe.ValidationError)
        return None
    try:
        parsed = UUID(candidate)
    except (ValueError, TypeError, AttributeError):
        frappe.throw(_("هوية إنشاء مسودة الطلب غير صالحة."), frappe.ValidationError)
    if parsed.version != 4 or parsed.int == 0:
        frappe.throw(_("هوية إنشاء مسودة الطلب غير صالحة."), frappe.ValidationError)
    return str(parsed)


def _current_user() -> str:
    user = str(frappe.session.user or "").strip()
    if not user or user == "Guest":
        frappe.throw(_("يجب تسجيل الدخول لاستعادة مسودة الطلب."), frappe.PermissionError)
    return user


def apply_new_order_creation_identity(document: Any) -> None:
    """Bind a client recovery identity to the authenticated insert actor.

    The token is an optional technical idempotency key around Frappe's native
    insert. Its unique DCO column is the atomic concurrency boundary: concurrent
    inserts with the same token cannot both commit. Normal DCO inserts without a
    local recovery session remain unchanged.
    """

    token = _creation_token(document.get(_TOKEN_FIELD), required=False)
    if token is None:
        document.set(_TOKEN_FIELD, None)
        document.set(_USER_FIELD, None)
        return
    document.set(_TOKEN_FIELD, token)
    document.set(_USER_FIELD, _current_user())


def enforce_creation_identity_immutability(document: Any) -> None:
    """Prevent an acknowledged server binding from being reassigned."""

    if document.is_new():
        return
    previous = document.get_doc_before_save()
    if previous is None:
        frappe.throw(_("تعذر التحقق من هوية إنشاء الطلب الحالية."), frappe.ValidationError)
    for fieldname in (_TOKEN_FIELD, _USER_FIELD):
        before = str(previous.get(fieldname) or "").strip()
        current = str(document.get(fieldname) or "").strip()
        if before != current:
            frappe.throw(_("لا يمكن تغيير هوية إنشاء الطلب بعد حفظه."), frappe.ValidationError)


@frappe.whitelist()
def reconcile_new_order_creation(creation_token: str) -> dict[str, Any]:
    """Resolve the current actor's creation token without accepting a DCO name."""

    token = _creation_token(creation_token, required=True)
    user = _current_user()
    resolved = frappe.db.get_value(
        _DCO_DOCTYPE,
        {_TOKEN_FIELD: token, _USER_FIELD: user},
        ["name", "modified"],
        as_dict=True,
    )
    if not resolved:
        # An actor may learn only that *their* token is unbound when they still
        # have authority to create a DCO. Another actor's token is indistinguishable
        # from an unused token.
        require_doctype_capability(
            Capability.CREATE_ORDER,
            message=_("لا تملك صلاحية إنشاء طلب قص جديد."),
        )
        return {"status": "NOT_FOUND"}

    document = frappe.get_doc(_DCO_DOCTYPE, resolved.name)
    if not frappe.has_permission(document, "read", user=user):
        frappe.throw(_("لا تملك صلاحية الوصول إلى الطلب المحفوظ."), frappe.PermissionError)
    return {
        "status": "CREATED",
        "door_cutting_order": str(resolved.name),
        "modified": str(resolved.modified or ""),
    }


__all__ = [
    "apply_new_order_creation_identity",
    "enforce_creation_identity_immutability",
    "reconcile_new_order_creation",
]
