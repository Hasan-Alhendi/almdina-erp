from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document


class CuttingPlan(Document):
    def validate(self) -> None:
        if self.revision and self.revision < 1:
            frappe.throw(_("Cutting Plan revision must be at least 1."))
        self._enforce_approved_immutability()

    def _enforce_approved_immutability(self) -> None:
        if self.is_new() or self.flags.get("allow_status_transition"):
            return

        old = self.get_doc_before_save()
        if not old:
            return

        if old.status == "Approved":
            frappe.throw(
                _(
                    "Approved Cutting Plan {0} is immutable. Create a new revision instead of editing it."
                ).format(self.name)
            )
