from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

from almdina_erp.almdina_erp.domain.cnc.tool_preset import ToolPresetError, normalize_tool_preset
from almdina_erp.almdina_erp.infrastructure.frappe.master_data_audit import (
    audit_deleted_document,
    audit_saved_document,
)
from almdina_erp.almdina_erp.infrastructure.frappe.master_data_references import (
    find_link_references,
    reference_summary,
)


_MESSAGES = {
    "preset_name_required": "Preset name is required.",
    "tool_name_required": "Tool name is required.",
    "tool_number_invalid": "Tool number must look like T9.",
    "tool_diameter_invalid": "Tool diameter must be a positive number of millimetres within the supported range.",
    "final_depth_invalid": "Final depth must be a positive number of millimetres within the supported range.",
    "spindle_speed_invalid": "Spindle speed must be a positive whole number of RPM within the supported range.",
    "feed_rate_invalid": "Feed rate must be a positive number of millimetres per minute within the supported range.",
    "plunge_rate_invalid": "Plunge rate must be a positive number of millimetres per minute within the supported range.",
    "pass_depth_invalid": "Pass depth must be a positive number of millimetres within the supported range.",
    "pass_depth_exceeds_final_depth": "Pass depth cannot be deeper than the final depth.",
}


class CNCToolPreset(Document):
    def validate(self) -> None:
        try:
            normalized = normalize_tool_preset(
                {
                    "preset_name": self.preset_name,
                    "tool_name": self.tool_name,
                    "tool_number": self.tool_number,
                    "tool_diameter_mm": self.tool_diameter_mm,
                    "final_depth_mm": self.final_depth_mm,
                    "spindle_speed_rpm": self.spindle_speed_rpm,
                    "feed_rate_mm_min": self.feed_rate_mm_min,
                    "plunge_rate_mm_min": self.plunge_rate_mm_min,
                    "pass_depth_mm": self.pass_depth_mm,
                    "enabled": self.enabled,
                }
            )
        except ToolPresetError as exc:
            frappe.throw(_(_MESSAGES[exc.code]), frappe.ValidationError)
        self.preset_name = normalized.preset_name
        self.tool_name = normalized.tool_name
        self.tool_number = normalized.tool_number
        self.tool_diameter_mm = normalized.tool_diameter_mm
        self.final_depth_mm = normalized.final_depth_mm
        self.spindle_speed_rpm = normalized.spindle_speed_rpm
        self.feed_rate_mm_min = normalized.feed_rate_mm_min
        self.plunge_rate_mm_min = normalized.plunge_rate_mm_min
        self.pass_depth_mm = normalized.pass_depth_mm
        self.enabled = 1 if normalized.enabled else 0

    def before_trash(self) -> None:
        references = find_link_references(self.doctype, self.name)
        if references:
            frappe.throw(
                _("This CNC tool preset is in use and cannot be deleted: {0}").format(
                    reference_summary(references)
                ),
                frappe.ValidationError,
            )

    def on_update(self) -> None:
        audit_saved_document(self)

    def on_trash(self) -> None:
        audit_deleted_document(self)


__all__ = ["CNCToolPreset"]
