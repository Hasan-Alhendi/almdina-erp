from __future__ import annotations

import frappe
from frappe.model.document import Document


class EdgeBandingType(Document):
    def validate(self) -> None:
        self.stock_uom = ""
        if self.item_code:
            self.stock_uom = frappe.db.get_value("Item", self.item_code, "stock_uom") or ""
