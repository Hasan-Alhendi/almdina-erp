from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

from almdina_erp.almdina_erp.domain.cnc.placement import PlacementError, normalize_cnc_machine
from almdina_erp.almdina_erp.domain.cnc.post_processor import PostProcessorError
from almdina_erp.almdina_erp.domain.cnc.post_processors import resolve_post_processor
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
    "offset_left_invalid": "The left stop must be zero or a positive number of centimetres.",
    "offset_right_invalid": "The right stop must be zero or a positive number of centimetres.",
    "offset_bottom_invalid": "The bottom stop must be zero or a positive number of centimetres.",
    "offset_top_invalid": "The top stop must be zero or a positive number of centimetres.",
    "cnc_machine_stops_unconfigured": (
        "Set the two stops for this work zero on the CNC machine. "
        "A stop from another edge is not copied across."
    ),
    "work_zero_invalid": "The selected work zero is not supported.",
    "work_zero_center_retired": (
        "This CNC machine still uses Center as its work zero. "
        "Choose Bottom Left, Bottom Right, Top Left, or Top Right before generating a new file."
    ),
    "cnc_machine_post_processor_unconfigured": (
        "Complete the CNC machine settings. Choose the post processor on the machine before generating a new NC file."
    ),
    "post_processor_unsupported": "The selected post processor is not supported.",
}


class CNCMachine(Document):
    def validate(self) -> None:
        try:
            normalized = normalize_cnc_machine(
                machine_name=self.machine_name,
                width_cm=self.width_cm,
                length_cm=self.length_cm,
                work_zero_position=self.work_zero_position,
                left_stop_cm=self.left_stop_cm,
                right_stop_cm=self.right_stop_cm,
                bottom_stop_cm=self.bottom_stop_cm,
                top_stop_cm=self.top_stop_cm,
            )
        except PlacementError as exc:
            frappe.throw(_(_MESSAGES.get(exc.code, exc.code)), frappe.ValidationError)
        self.machine_name = normalized.name
        self.width_cm = normalized.width_cm
        self.length_cm = normalized.length_cm
        self.work_zero_position = normalized.work_zero_position
        self.left_stop_cm = normalized.left_stop_cm
        self.right_stop_cm = normalized.right_stop_cm
        self.bottom_stop_cm = normalized.bottom_stop_cm
        self.top_stop_cm = normalized.top_stop_cm
        try:
            self.post_processor = resolve_post_processor(self.post_processor, required=True)
        except PostProcessorError as exc:
            code = (
                "cnc_machine_post_processor_unconfigured"
                if exc.code in {"post_processor_required", "post_processor_unsupported"}
                else exc.code
            )
            frappe.throw(_(_MESSAGES.get(code, code)), frappe.ValidationError)
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
