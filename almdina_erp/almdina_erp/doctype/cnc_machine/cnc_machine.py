from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

from almdina_erp.almdina_erp.domain.cnc.placement import PlacementError, normalize_cnc_machine
from almdina_erp.almdina_erp.infrastructure.frappe.master_data_audit import (
    audit_deleted_document,
    audit_saved_document,
)
from almdina_erp.almdina_erp.infrastructure.frappe.master_data_references import (
    find_link_references,
    reference_summary,
)


_MESSAGES = {
    "cnc_machine_name_required": "CNC machine name is required.",
    "cnc_machine_width_invalid": "CNC machine width must be a positive number of centimetres.",
    "cnc_machine_length_invalid": "CNC machine length must be a positive number of centimetres.",
}


class CNCMachine(Document):
    def validate(self) -> None:
        try:
            normalized = normalize_cnc_machine(
                machine_name=self.machine_name,
                width_cm=self.width_cm,
                length_cm=self.length_cm,
            )
        except PlacementError as exc:
            frappe.throw(_(_MESSAGES.get(exc.code, exc.code)), frappe.ValidationError)
        self.machine_name = normalized.name
        self.width_cm = normalized.width_cm
        self.length_cm = normalized.length_cm
        self.enabled = 1 if int(self.enabled or 0) else 0

    def on_update(self) -> None:
        audit_saved_document(self)

    def on_trash(self) -> None:
        references = find_link_references(self.doctype, self.name)
        if references:
            frappe.throw(
                _("This CNC machine is in use and cannot be deleted: {0}").format(
                    reference_summary(references)
                ),
                frappe.ValidationError,
            )
        audit_deleted_document(self)


__all__ = ["CNCMachine"]
