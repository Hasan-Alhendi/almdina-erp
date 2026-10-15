"""Save the Desk language of the signed-in user."""

from __future__ import annotations

import frappe
from frappe import _

from almdina_erp.almdina_erp.infrastructure.frappe.language_catalog import (
    stored_language_code,
)
from almdina_erp.almdina_erp.infrastructure.frappe.ui_language_catalog import (
    resolve_ui_language,
)


@frappe.whitelist(methods=["POST"])
def set_current_user_language(language: str) -> dict[str, str]:
    """Store ``User.language`` for ``frappe.session.user`` and return that code.

    The client cannot name a user or an email. Guest is rejected. The language
    must belong to the Almdina UI catalog, which is checked again on the server.
    """

    if frappe.session.user in (None, "", "Guest"):
        frappe.throw(
            _("You must be logged in to change the interface language."),
            frappe.PermissionError,
        )
    code = resolve_ui_language(language)
    if not code:
        frappe.throw(
            _("The selected language is not available."),
            frappe.ValidationError,
        )
    user = frappe.get_doc("User", frappe.session.user)
    if stored_language_code(user.language or "").lower() == stored_language_code(code).lower():
        return {"language": code}
    user.language = code
    # Confined to this save. The document is always the session user, so the
    # client cannot point the write at somebody else. ``save`` still runs User
    # validation and on_update, including locale settings and cache clearing.
    user.save(ignore_permissions=True)
    return {"language": code}


__all__ = ["set_current_user_language"]
