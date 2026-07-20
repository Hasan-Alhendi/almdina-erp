from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document


class ProductionIncident(Document):
    def validate(self) -> None:
        if self.production_stage:
            stage_order = frappe.db.get_value("Production Stage", self.production_stage, "door_cutting_order")
            if stage_order and stage_order != self.door_cutting_order:
                frappe.throw(_("The selected Production Stage belongs to another order."))
