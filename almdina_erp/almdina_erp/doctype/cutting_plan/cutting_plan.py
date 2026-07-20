from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint


class CuttingPlan(Document):
    def validate(self) -> None:
        if self.revision and self.revision < 1:
            frappe.throw(_("Cutting Plan revision must be at least 1."))
        if self.plan_kind == "Replacement" and not self.replacement_piece:
            frappe.throw(_("A Replacement cutting plan must reference its Replacement Piece."))
        self._enforce_approved_immutability()

    def on_update(self) -> None:
        if self.status != "Approved" or (self.plan_kind or "Order") != "Order":
            return

        old = self.get_doc_before_save()
        became_approved = self.is_new() or not old or old.status != "Approved"
        if not became_approved:
            return

        settings = frappe.get_single("Almdina ERP Settings")
        if cint(settings.reserve_stock_on_approval):
            from almdina_erp.almdina_erp.services.stock_service import create_order_reservation

            create_order_reservation(self.door_cutting_order)

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
