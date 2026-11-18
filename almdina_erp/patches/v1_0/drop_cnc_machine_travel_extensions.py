"""Drop the cutter-travel extension columns from CNC Machine.

Those columns treated the machine bed as a cutter-travel allowance. The bed
bounds the sheet only. The patch is idempotent: a site that never created the
columns, or that already dropped them, is left unchanged. Machine width,
length, and operational-file rows are not rewritten.
"""

from __future__ import annotations

import frappe


_COLUMNS = (
    "cutter_travel_left_extension_mm",
    "cutter_travel_right_extension_mm",
    "cutter_travel_bottom_extension_mm",
    "cutter_travel_top_extension_mm",
)


def execute() -> None:
    if not frappe.db.table_exists("CNC Machine"):
        return
    for column in _COLUMNS:
        if frappe.db.has_column("CNC Machine", column):
            frappe.db.sql_ddl(f"alter table `tabCNC Machine` drop column `{column}`")
