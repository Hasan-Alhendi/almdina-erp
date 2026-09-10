from __future__ import annotations

import frappe
from frappe.model.document import Document


class ProductionStageDefinition(Document):
    def validate(self) -> None:
        self.stage_code = str(self.stage_code or "").strip()
        self.stage_label = str(self.stage_label or "").strip()
        self.description = str(self.description or "").strip()
        if not self.stage_code:
            frappe.throw("رمز المرحلة مطلوب.", frappe.ValidationError)
        if not self.stage_label:
            frappe.throw("اسم المرحلة مطلوب.", frappe.ValidationError)

    def before_trash(self) -> None:
        if frappe.db.exists(
            "Production Routing Stage",
            {"stage_definition": self.name},
        ):
            frappe.throw(
                "هذه المرحلة مستخدمة في مسار إنتاج. عطّلها بدل حذفها.",
                frappe.ValidationError,
            )
