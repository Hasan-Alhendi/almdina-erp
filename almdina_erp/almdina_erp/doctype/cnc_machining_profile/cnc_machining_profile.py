"""Catalog record for one ArtCAM profile.

The stored tool copy belongs to this profile. Saving it does not rewrite the
tool, a sheet file, or a calculated toolpath. A profile does not link a machine.
"""

from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.model.document import Document

from almdina_erp.almdina_erp.domain.cnc.artcam_machining import (
    MachiningSetupError,
    new_machining_id,
    normalize_profile,
)
from almdina_erp.almdina_erp.infrastructure.frappe.cnc_operational_file_repository import (
    known_tool_presets,
)
from almdina_erp.almdina_erp.infrastructure.frappe.master_data_audit import (
    audit_deleted_document,
    audit_saved_document,
)
from almdina_erp.almdina_erp.infrastructure.frappe.master_data_references import (
    find_link_references,
    reference_summary,
)


_MESSAGES = {
    "profile_name_required": "Enter a profile name.",
    "profile_id_invalid": "The profile identity is not valid.",
    "tool_preset_required": "Choose a tool for this profile.",
    "preset_not_found": "The selected CNC tool preset does not exist.",
    "preset_disabled": "The selected CNC tool preset is disabled.",
    "safe_z_invalid": "Safe Z must be zero or a positive number of millimetres within the supported range.",
    "home_x_invalid": "Home X must be a finite number of millimetres.",
    "home_y_invalid": "Home Y must be a finite number of millimetres.",
    "home_z_invalid": "Home Z must be zero or a positive number of millimetres within the supported range.",
    "final_depth_invalid": "Final depth must be a positive number of millimetres within the supported range.",
    "pass_depth_exceeds_final_depth": "Pass depth cannot be deeper than the final depth.",
    "description_required": "Enter the tool description.",
    "tool_number_invalid": "Tool number must be a whole number such as 9.",
    "tool_type_unsupported": "Only a Ball Nose tool can be created here.",
    "tool_units_invalid": "Tool units must be mm.",
    "rate_units_invalid": "Rate units must be mm/sec.",
    "tool_diameter_invalid": "Diameter must be a positive number of millimetres.",
    "stepdown_invalid": "Stepdown must be a positive number of millimetres.",
    "final_tool_offset_invalid": "Final tool offset must be zero or a positive number of millimetres.",
    "stepover_invalid": "Enter the stepover size and its percent of diameter.",
    "spindle_speed_invalid": "Spindle speed must be a positive whole number of RPM.",
    "feed_rate_invalid": "Feed rate must be a positive number of millimetres per second.",
    "plunge_rate_invalid": "Plunge rate must be a positive number of millimetres per second.",
    "notes_invalid": "The tool notes are too long.",
}


def _object(value: object) -> dict:
    if isinstance(value, str):
        if not value.strip():
            return {}
        parsed = json.loads(value)
        return dict(parsed) if isinstance(parsed, dict) else {}
    if isinstance(value, dict):
        return dict(value)
    return {}


class CNCMachiningProfile(Document):
    def before_insert(self) -> None:
        if not str(self.profile_id or "").strip():
            self.profile_id = new_machining_id("profile")

    def validate(self) -> None:
        if not str(self.profile_id or "").strip():
            self.profile_id = new_machining_id("profile")
        raw = {
            "name": self.profile_name,
            "profile_id": self.profile_id,
            "tool_preset": self.tool_preset,
            "tool_values": _object(self.tool_values_json),
            "final_depth_mm": self.final_depth_mm,
            "safe_z_mm": self.safe_z_mm,
            "home_x_mm": self.home_x_mm,
            "home_y_mm": self.home_y_mm,
            "home_z_mm": self.home_z_mm,
        }
        previous = None if self.is_new() else self.get_doc_before_save()
        if previous is not None and str(previous.tool_preset or "") != str(self.tool_preset or ""):
            raw["tool_values"] = {}
        try:
            profile = normalize_profile(
                raw,
                known_tools=known_tool_presets(),
                profile_id=self.profile_id,
            )
        except MachiningSetupError as exc:
            frappe.throw(_(_MESSAGES.get(exc.code, "The profile is not valid.")), frappe.ValidationError)
        self.profile_id = profile["profile_id"]
        self.profile_name = profile["name"]
        self.tool_preset = profile["tool_preset"]
        self.tool_values_json = profile["tool_values"]
        self.final_depth_mm = profile["final_depth_mm"]
        self.safe_z_mm = profile["safe_z_mm"]
        self.home_x_mm = profile["home_x_mm"]
        self.home_y_mm = profile["home_y_mm"]
        self.home_z_mm = profile["home_z_mm"]
        self.enabled = 1 if int(self.enabled or 0) else 0

    def on_update(self) -> None:
        audit_saved_document(self)

    def on_trash(self) -> None:
        references = find_link_references(self.doctype, self.name)
        if references:
            frappe.throw(
                _("This machining profile is in use and cannot be deleted: {0}").format(
                    reference_summary(references)
                ),
                frappe.ValidationError,
            )
        if _association_uses(str(self.profile_id or "")):
            frappe.throw(
                _("This machining profile is used by a vector association on an operational file and cannot be deleted."),
                frappe.ValidationError,
            )
        audit_deleted_document(self)


def _association_uses(profile_id: str) -> int:
    if not profile_id or not frappe.db.exists("DocType", "CNC Operational File"):
        return 0
    uses = 0
    for raw in frappe.get_all(
        "CNC Operational File",
        pluck="vector_associations_json",
        limit_page_length=0,
    ):
        parsed = json.loads(raw) if isinstance(raw, str) and raw else raw
        if not isinstance(parsed, list):
            continue
        uses += sum(
            1
            for row in parsed
            if isinstance(row, dict) and str(row.get("profile_id") or "") == profile_id
        )
    return uses


__all__ = ["CNCMachiningProfile"]
