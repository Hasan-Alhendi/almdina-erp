from __future__ import annotations

import frappe
from frappe.model.document import Document

from almdina_erp.almdina_erp.infrastructure.frappe.order_status_metadata import (
    sync_order_status_options,
)


class ProductionStageDefinition(Document):
    def validate(self) -> None:
        self.stage_code = str(self.stage_code or "").strip()
        self.stage_label = str(self.stage_label or "").strip()
        self.description = str(self.description or "").strip()
        if not self.stage_code:
            frappe.throw("رمز المرحلة مطلوب.", frappe.ValidationError)
        if not self.stage_label:
            frappe.throw("اسم المرحلة مطلوب.", frappe.ValidationError)

        if not self.is_new():
            stored_code = frappe.db.get_value(
                self.doctype,
                self.name,
                "stage_code",
            )
            if stored_code and str(stored_code) != self.stage_code:
                frappe.throw(
                    "رمز المرحلة هو هوية ثابتة ولا يمكن تغييره بعد الإنشاء.",
                    frappe.ValidationError,
                )

        duplicate_label = frappe.db.exists(
            self.doctype,
            {
                "stage_label": self.stage_label,
                "name": ["!=", self.name or ""],
            },
        )
        if duplicate_label:
            frappe.throw(
                "اسم المرحلة مستخدم مسبقًا. يجب أن يكون اسم كل مرحلة فريدًا.",
                frappe.ValidationError,
            )

    def on_update(self) -> None:
        sync_order_status_options()

    def before_trash(self) -> None:
        if frappe.db.exists(
            "Production Routing Stage",
            {"stage_definition": self.name},
        ):
            frappe.throw(
                "هذه المرحلة مستخدمة في مسار إنتاج. عطّلها بدل حذفها.",
                frappe.ValidationError,
            )

    def after_delete(self) -> None:
        sync_order_status_options()
