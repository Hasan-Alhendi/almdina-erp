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
        ordered = sorted(self.stages, key=lambda row: cint(row.sequence))
        for index, row in enumerate(ordered, start=1):
            sequence = cint(row.sequence)
            if sequence <= 0:
                frappe.throw(_("Routing stage sequence must be greater than zero."))
            if sequence in sequences:
                frappe.throw(_("Routing stage sequence {0} is duplicated.").format(sequence))
            if row.stage_type in stage_types:
                frappe.throw(_("Routing stage {0} is duplicated.").format(row.stage_type))
            sequences.add(sequence)
            stage_types.add(row.stage_type)
            row.idx = index

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
