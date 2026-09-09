from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint

from almdina_erp.almdina_erp.infrastructure.frappe.master_data_audit import (
    audit_deleted_document,
    audit_saved_document,
)
from almdina_erp.almdina_erp.infrastructure.frappe.master_data_references import (
    find_link_references,
    reference_summary,
)


class ProductionWorkflowStage(Document):
    """Stable workflow-stage identity shared by every production route."""

    def validate(self) -> None:
        self.stage_code = str(self.stage_code or "").strip()
        self.stage_label = str(self.stage_label or "").strip()
        self.kanban_order = cint(self.kanban_order)
        if not self.stage_code:
            frappe.throw(_("رمز مرحلة الإنتاج مطلوب."), frappe.ValidationError)
        if not self.stage_label:
            frappe.throw(_("اسم مرحلة الإنتاج مطلوب."), frappe.ValidationError)
        if self.kanban_order < 0:
            frappe.throw(_("ترتيب العرض لا يمكن أن يكون سالبًا."), frappe.ValidationError)
        self._enforce_immutable_code()
        self._protect_enabled_routes()

    def _enforce_immutable_code(self) -> None:
        if self.is_new() or not frappe.db.exists(self.doctype, self.name):
            return
        previous = str(frappe.db.get_value(self.doctype, self.name, "stage_code") or "").strip()
        if previous and previous != self.stage_code:
            frappe.throw(
                _("رمز المرحلة ثابت بعد الإنشاء. غيّر الاسم الظاهر بدلًا من الرمز."),
                frappe.ValidationError,
            )

    def _protect_enabled_routes(self) -> None:
        if not cint(self.disabled) or self.is_new():
            return
        route = frappe.db.sql(
            """
            select prs.parent
              from `tabProduction Routing Stage` prs
              join `tabProduction Routing` pr on pr.name = prs.parent
             where prs.workflow_stage = %s
               and ifnull(prs.required, 0) = 1
               and ifnull(pr.disabled, 0) = 0
             limit 1
            """,
            (self.name,),
            as_dict=True,
        )
        if route:
            frappe.throw(
                _("عطّل المسار {0} أو أزل المرحلة منه قبل تعطيل هذه المرحلة.").format(route[0].parent),
                frappe.ValidationError,
            )

    def before_trash(self) -> None:
        references = find_link_references(self.doctype, self.name)
        if references:
            frappe.throw(
                _("مرحلة الإنتاج مستخدمة ولا يمكن حذفها: {0}").format(reference_summary(references)),
                frappe.ValidationError,
            )

    def on_update(self) -> None:
        audit_saved_document(self)

    def on_trash(self) -> None:
        audit_deleted_document(self)


__all__ = ["ProductionWorkflowStage"]
