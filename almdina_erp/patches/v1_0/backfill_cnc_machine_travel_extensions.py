"""Initialize cutter-travel extensions without changing existing machine beds."""

from __future__ import annotations

import frappe


_FIELDS = (
    "cutter_travel_left_extension_mm",
    "cutter_travel_right_extension_mm",
    "cutter_travel_bottom_extension_mm",
    "cutter_travel_top_extension_mm",
)


def execute() -> None:
    if not frappe.db.table_exists("CNC Machine"):
        return
    for fieldname in _FIELDS:
        if not frappe.db.has_column("CNC Machine", fieldname):
            continue
        frappe.db.sql(
            f"""
            update `tabCNC Machine`
               set `{fieldname}` = 0
             where `{fieldname}` is null
            """
        )
