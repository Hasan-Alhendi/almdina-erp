from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint


class ProductionRouting(Document):
    def validate(self) -> None:
        if not self.stages:
            frappe.throw(_("Production Routing requires at least one stage."))

        sequences: set[int] = set()
        stage_types: set[str] = set()
        for row in self.stages:
            sequence = cint(row.sequence)
            if sequence <= 0:
                frappe.throw(_("Routing stage sequence must be greater than zero."))
            if sequence in sequences:
                frappe.throw(_("Routing stage sequence {0} is duplicated.").format(sequence))
            if row.stage_type in stage_types:
                frappe.throw(_("Routing stage {0} is duplicated.").format(row.stage_type))
            sequences.add(sequence)
            stage_types.add(row.stage_type)
