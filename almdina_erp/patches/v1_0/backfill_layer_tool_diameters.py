from __future__ import annotations

import frappe


_FIELDS = (
    "liner_tool_diameter_mm",
    "handle_recess_tool_diameter_mm",
    "rear_groove_tool_diameter_mm",
)


def execute() -> None:
    """Copy a historical blade into blank layer diameters.

    A second migrate changes nothing. Kerf of zero stays blank because export
    already refuses a non-positive machining diameter. Factory defaults are
    not invented here.
    """

    if not frappe.db.has_column("Cutting Plan", "kerf_mm"):
        return
    for fieldname in _FIELDS:
        if not frappe.db.has_column("Cutting Plan", fieldname):
            continue
        frappe.db.sql(
            f"""
            update `tabCutting Plan`
               set `{fieldname}` = kerf_mm
             where `{fieldname}` is null
               and ifnull(kerf_mm, 0) > 0
            """
        )
