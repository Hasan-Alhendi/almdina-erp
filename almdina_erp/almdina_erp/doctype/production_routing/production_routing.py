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
from almdina_erp.almdina_erp.infrastructure.frappe.system_role_policy import (
    is_protected_system_role,
)


class ProductionRouting(Document):
    def validate(self) -> None:
        if not self.stages:
            frappe.throw(_("يجب أن يحتوي مسار الإنتاج على مرحلة واحدة على الأقل."))

        stage_names = {
            str(row.stage_definition or "").strip()
            for row in self.stages
            if str(row.stage_definition or "").strip()
        }
        definition_rows = frappe.get_all(
            "Production Stage Definition",
            filters={"name": ["in", sorted(stage_names)]} if stage_names else {},
            fields=["name", "stage_label", "disabled"],
        ) if stage_names else []
        definitions = {str(row.name): row for row in definition_rows}

        sequences: set[int] = set()
        stage_definitions: set[str] = set()
        required_rows = []
        planning_rows = []
        ordered = sorted(self.stages, key=lambda row: cint(row.sequence))
        for index, row in enumerate(ordered, start=1):
            row.stage_definition = str(row.stage_definition or "").strip()
            row.operational_role = str(row.operational_role or "").strip()
            sequence = cint(row.sequence)
            if sequence <= 0:
                frappe.throw(_("ترتيب مرحلة الإنتاج يجب أن يكون أكبر من الصفر."))
            if sequence in sequences:
                frappe.throw(_("ترتيب المرحلة رقم {0} مكرر داخل المسار.").format(sequence))
            if not row.stage_definition:
                frappe.throw(_("يجب اختيار المرحلة من مكتبة مراحل الإنتاج."))
            definition = definitions.get(row.stage_definition)
            if not definition:
                frappe.throw(
                    _("المرحلة {0} غير موجودة في مكتبة مراحل الإنتاج.").format(
                        row.stage_definition
                    )
                )
            if cint(definition.disabled):
                frappe.throw(
                    _("المرحلة {0} معطّلة ولا يمكن استخدامها في المسار.").format(
                        definition.stage_label or row.stage_definition
                    )
                )
            if row.stage_definition in stage_definitions:
                frappe.throw(
                    _("مرحلة الإنتاج {0} مكررة داخل المسار.").format(
                        definition.stage_label or row.stage_definition
                    )
                )

            is_required = bool(cint(row.required))
            is_planning = bool(cint(getattr(row, "is_planning_stage", 0)))
            if is_planning and not is_required:
                frappe.throw(
                    _("مرحلة التخطيط يجب أن تكون ضمن المسار وفعالة."),
                    frappe.ValidationError,
                )
            if is_required:
                required_rows.append(row)
                if not row.operational_role:
                    frappe.throw(
                        _("يجب تحديد الدور التشغيلي للمرحلة {0}.").format(
                            definition.stage_label or row.stage_definition
                        )
                    )
                self._validate_operational_role(
                    row.operational_role,
                    str(definition.stage_label or row.stage_definition),
                )
                if is_planning:
                    planning_rows.append(row)

            sequences.add(sequence)
            stage_definitions.add(row.stage_definition)
            row.idx = index

        if not required_rows:
            frappe.throw(_("يجب أن يحتوي مسار الإنتاج على مرحلة فعالة واحدة على الأقل."))
        if len(planning_rows) > 1:
            frappe.throw(
                _("يمكن تحديد مرحلة تخطيط واحدة فقط داخل مسار الإنتاج."),
                frappe.ValidationError,
            )
        if planning_rows and planning_rows[0] is not required_rows[0]:
            frappe.throw(
                _("مرحلة التخطيط يجب أن تكون أول مرحلة فعالة في مسار الإنتاج."),
                frappe.ValidationError,
            )

        self._prevent_active_route_mutation()

    @staticmethod
    def _validate_operational_role(role: str, stage_label: str) -> None:
        if is_protected_system_role(role):
            frappe.throw(
                _("لا يمكن استخدام الدور المحمي {0} كدور تشغيلي للمرحلة {1}.").format(
                    role,
                    stage_label,
                ),
                frappe.ValidationError,
            )
        if not frappe.db.exists("Role", role):
            frappe.throw(
                _("الدور التشغيلي {0} المحدد للمرحلة {1} غير موجود.").format(
                    role,
                    stage_label,
                ),
                frappe.ValidationError,
            )
        role_meta = frappe.get_meta("Role")
        if role_meta.has_field("disabled") and cint(
            frappe.db.get_value("Role", role, "disabled")
        ):
            frappe.throw(
                _("الدور التشغيلي {0} معطّل ولا يمكن إسناد مرحلة إنتاج إليه.").format(role),
                frappe.ValidationError,
            )

    def _prevent_active_route_mutation(self) -> None:
        """Keep an in-flight order on the route definition it was dispatched with."""

        if self.is_new() or not frappe.db.exists("Production Routing", self.name):
            return
        previous_disabled = cint(
            frappe.db.get_value("Production Routing", self.name, "disabled")
        )
        previous_rows = frappe.get_all(
            "Production Routing Stage",
            filters={"parent": self.name, "parenttype": "Production Routing"},
            fields=[
                "sequence",
                "stage_definition",
                "operational_role",
                "required",
                "is_planning_stage",
            ],
            order_by="sequence asc, idx asc",
        )
        previous = [
            (
                cint(row.sequence),
                str(row.stage_definition or ""),
                str(row.operational_role or ""),
                cint(row.required),
                cint(row.is_planning_stage),
            )
            for row in previous_rows
        ]
        current = [
            (
                cint(row.sequence),
                str(row.stage_definition or ""),
                str(row.operational_role or ""),
                cint(row.required),
                cint(getattr(row, "is_planning_stage", 0)),
            )
            for row in sorted(self.stages or (), key=lambda item: cint(item.sequence))
        ]
        changed = previous != current or (not previous_disabled and cint(self.disabled))
        if not changed:
            return
        active = frappe.db.exists(
            "Door Cutting Order",
            {
                "production_path": self.name,
                "current_production_stage": ["is", "set"],
                "status": ["not in", ["Delivered", "Cancelled"]],
            },
        )
        if active:
            frappe.throw(
                _(
                    "هذا المسار مستخدم حاليًا في طلبات قيد الإنتاج. أنهِ هذه الطلبات أو ألغها أو أعدها قبل تعديل مراحل المسار."
                ),
                frappe.ValidationError,
            )

    def before_trash(self) -> None:
        references = find_link_references(self.doctype, self.name)
        if references:
            frappe.throw(
                _("مسار الإنتاج مستخدم ولا يمكن حذفه: {0}").format(
                    reference_summary(references)
                ),
                frappe.ValidationError,
            )

    def on_update(self) -> None:
        audit_saved_document(self)

    def on_trash(self) -> None:
        audit_deleted_document(self)


__all__ = ["ProductionRouting"]
