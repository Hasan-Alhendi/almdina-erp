"""Restore the profile tool snapshot and drop the unused Profile-to-Machine link.

This patch does not delete catalog records and does not repeat the ArtCAM
cleanup. The cleanup marker stays untouched.
"""

from __future__ import annotations

import frappe


def execute() -> None:
    doctype = "CNC Machining Profile"
    table = "tabCNC Machining Profile"
    if not frappe.db.table_exists(doctype):
        return
    if frappe.db.has_column(doctype, "cnc_machine"):
        frappe.db.sql_ddl(f"alter table `{table}` drop column `cnc_machine`")
    if not frappe.db.has_column(doctype, "tool_values_json"):
        frappe.db.sql_ddl(f"alter table `{table}` add column `tool_values_json` json")
