from __future__ import annotations

import uuid

import frappe
from frappe import _
from frappe.model.document import Document


class AlmdinaRoleMetadata(Document):
    """Private metadata attached to a dynamic Frappe Role."""

    def before_insert(self) -> None:
        self.role_uid = self.role_uid or str(uuid.uuid4())
        self.managed_by_almdina = 1

    def validate(self) -> None:
        if not frappe.db.exists("Role", self.role):
            frappe.throw(_("Role does not exist."))
        if not self.is_new():
            stored_uid = frappe.db.get_value(
                "Almdina Role Metadata",
                self.name,
                "role_uid",
            )
            if stored_uid and self.role_uid != stored_uid:
                frappe.throw(_("Role metadata identity is immutable."))


__all__ = ["AlmdinaRoleMetadata"]
