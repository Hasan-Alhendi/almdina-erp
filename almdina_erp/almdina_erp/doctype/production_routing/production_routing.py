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


class ProductionRouting(Document):
    def validate(self) -> None:
        if not self.stages:
            frappe.throw(_("Production Routing requires at least one stage."))

        sequences: set[int] = set()
        stage_types: set[str] = set()
        required_count = 0
        ordered = sorted(self.stages, key=lambda row: cint(row.sequence))
        for index, row in enumerate(ordered, start=1):
            row.stage_type = str(row.stage_type or "").strip()
            row.department_label = str(row.department_label or "").strip()
            row.operational_role = str(row.operational_role or "").strip()
            sequence = cint(row.sequence)
            if sequence <= 0:
                frappe.throw(_("Routing stage sequence must be greater than zero."))
            if sequence in sequences:
                frappe.throw(_("Routing stage sequence {0} is duplicated.").format(sequence))
            if not row.stage_type:
                frappe.throw(_("Routing stage code is required."))
            if row.stage_type in stage_types:
                frappe.throw(_("Routing stage {0} is duplicated.").format(row.stage_type))
            if cint(row.required):
                required_count += 1
                if not str(row.department_label or "").strip():
                    frappe.throw(
                        _("Department label is required for stage {0}.").format(
                            row.stage_type
                        )
                    )
                if not str(row.operational_role or "").strip():
                    frappe.throw(
                        _("Operational role is required for stage {0}.").format(
                            row.stage_type
                        )
                    )
            sequences.add(sequence)
            stage_types.add(row.stage_type)
            row.idx = index
        if not required_count:
            frappe.throw(_("Production Routing requires at least one required stage."))

        self._prevent_active_route_mutation()

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
                "stage_type",
                "department_label",
                "operational_role",
                "required",
            ],
            order_by="sequence asc, idx asc",
        )
        previous = [
            (
                cint(row.sequence),
                str(row.stage_type or ""),
                str(row.department_label or ""),
                str(row.operational_role or ""),
                cint(row.required),
            )
            for row in previous_rows
        ]
        current = [
            (
                cint(row.sequence),
                str(row.stage_type or ""),
                str(row.department_label or ""),
                str(row.operational_role or ""),
                cint(row.required),
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
                    "This route is used by active orders. Finish, cancel, or return those orders before changing its stages."
                ),
                frappe.ValidationError,
            )

    def before_trash(self) -> None:
        references = find_link_references(self.doctype, self.name)
        if references:
            frappe.throw(
                _("This production routing is in use and cannot be deleted: {0}").format(
                    reference_summary(references)
                ),
                frappe.ValidationError,
            )

    def on_update(self) -> None:
        audit_saved_document(self)

    def on_trash(self) -> None:
        audit_deleted_document(self)


__all__ = ["ProductionRouting"]
