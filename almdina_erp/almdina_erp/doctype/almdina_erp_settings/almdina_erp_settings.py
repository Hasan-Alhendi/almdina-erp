from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document


class AlmdinaERPSettings(Document):
    """Factory settings are mutated only through trusted field-aware services."""

    def before_save(self) -> None:
        trusted_write = bool(getattr(self.flags, "ignore_permissions", False))
        lifecycle_write = any(
            bool(getattr(frappe.flags, flag, False))
            for flag in ("in_install", "in_migrate", "in_patch")
        )
        if trusted_write or lifecycle_write:
            return
        frappe.throw(
            _("Use the Almdina Factory Settings page to update these values."),
            frappe.PermissionError,
        )


__all__ = ["AlmdinaERPSettings"]
