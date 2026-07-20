from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document


class MaterialReservation(Document):
    def validate(self) -> None:
        if not self.is_new() and not self.flags.get("allow_status_transition"):
            frappe.throw(_("Material Reservations are controlled by the production workflow and cannot be edited manually."))
