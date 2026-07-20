from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document


class ProductionStageEvent(Document):
    def validate(self) -> None:
        if not self.is_new():
            frappe.throw(_("Production Stage Events are append-only and cannot be edited."))

    def on_trash(self) -> None:
        if not frappe.flags.in_uninstall:
            frappe.throw(_("Production Stage Events are audit records and cannot be deleted."))
