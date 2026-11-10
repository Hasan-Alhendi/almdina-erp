from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint

from almdina_erp.almdina_erp.domain.cnc.artcam_machining import machining_tool_uses
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
        if not self.enabled and not self.is_new():
            previous = self.get_doc_before_save()
            if previous is not None and int(previous.enabled or 0):
                live_uses, _snapshot_uses = _saved_machining_uses(self.name)
                if live_uses:
                    frappe.throw(
                        _("This tool is still selected by a profile or vector association. Calculated toolpaths keep their own copy, but those live selections must choose another tool before this one can be disabled."),
                        frappe.ValidationError,
                    )

    def before_trash(self) -> None:
        from almdina_erp.almdina_erp.services.production_settings_service import (
            assert_tool_preset_can_be_deleted,
        )

        assert_tool_preset_can_be_deleted(self.name)
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


def _saved_machining_uses(name: str) -> tuple[int, int]:
    """Count profile/association selections separately from frozen snapshot copies."""

    live_uses = 0
    snapshot_uses = 0
    for row in frappe.get_all(
        "CNC Operational File",
        fields=["machining_profiles_json", "vector_associations_json", "toolpath_snapshots_json"],
    ):
        uses = machining_tool_uses(
            name,
            profiles=_json_rows(row.machining_profiles_json),
            associations=_json_rows(row.vector_associations_json),
            snapshots=_json_rows(row.toolpath_snapshots_json),
        )
        live_uses += uses["profiles"] + uses["associations"]
        snapshot_uses += uses["snapshots"]
    if frappe.db.exists("DocType", "CNC Machining Profile"):
        live_uses += cint(frappe.db.count("CNC Machining Profile", {"tool_preset": name}))
    return live_uses, snapshot_uses


def _json_rows(raw: object) -> list:
    if not raw:
        return []
    parsed = json.loads(raw) if isinstance(raw, str) else raw
    return list(parsed or []) if isinstance(parsed, list) else []


__all__ = ["CNCToolPreset"]
