from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt


class ReplacementPiece(Document):
    def validate(self) -> None:
        if flt(self.width_cm) <= 0 or flt(self.length_cm) <= 0:
            frappe.throw(_("Replacement dimensions must be greater than zero."))
        if cint(self.qty) <= 0:
            frappe.throw(_("Replacement quantity must be a positive integer."))

        if self.incident:
            incident_order = frappe.db.get_value("Production Incident", self.incident, "door_cutting_order")
            if incident_order and incident_order != self.door_cutting_order:
                frappe.throw(_("The selected incident belongs to another order."))

        if self.selected_remnant:
            remnant = frappe.db.get_value(
                "Board Remnant",
                self.selected_remnant,
                ["board_item", "status", "reserved_for_order"],
                as_dict=True,
            )
            if not remnant or remnant.board_item != self.board_item:
                frappe.throw(_("Selected remnant does not match the replacement board item."))
            if remnant.status == "Reserved" and remnant.reserved_for_order not in {None, "", self.door_cutting_order}:
                frappe.throw(_("Selected remnant is reserved for another order."))

        # Internal production failure must never silently become a customer charge.
        self.charge_customer = 0
