from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document


class AlmdinaMasterDataAudit(Document):
    """Immutable audit trail for sensitive factory configuration changes."""

    def before_insert(self) -> None:
        self.changed_by = self.changed_by or frappe.session.user
        self.changed_on = self.changed_on or frappe.utils.now()

    def validate(self) -> None:
        if not self.is_new():
            frappe.throw(_("Master data audit records are immutable."))


__all__ = ["AlmdinaMasterDataAudit"]
