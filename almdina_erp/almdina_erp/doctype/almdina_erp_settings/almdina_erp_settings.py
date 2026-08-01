from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document


class AlmdinaERPSettings(Document):
    """Factory settings are mutated only through the field-aware service."""

    def before_save(self) -> None:
        if any(
            bool(getattr(frappe.flags, flag, False))
            for flag in (
                "in_install",
                "in_migrate",
                "in_patch",
                "allow_almdina_factory_settings_write",
            )
        ):
            return
        frappe.throw(
            _("Use the Almdina Factory Settings page to update these values."),
            frappe.PermissionError,
        )


__all__ = ["AlmdinaERPSettings"]
