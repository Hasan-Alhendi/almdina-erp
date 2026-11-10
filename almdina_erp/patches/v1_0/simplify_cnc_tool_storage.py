"""Move tool storage onto Tool Name, mm/sec, and Stepdown.

Existing rows are copied before the old columns are dropped. No catalog
records are deleted, and the ArtCAM cleanup marker is not changed.
"""

from __future__ import annotations

import frappe

_FIXED = (
    ("tool_type", "Ball Nose"),
    ("tool_units", "mm"),
    ("rate_units", "mm/sec"),
)


def execute() -> None:
    doctype = "CNC Tool Preset"
    table = "tabCNC Tool Preset"
    if not frappe.db.table_exists(doctype):
        return
    if frappe.db.has_column(doctype, "preset_name") and frappe.db.has_column(doctype, "tool_name"):
        frappe.db.sql(
            f"""
            update `{table}`
            set tool_name = preset_name
            where ifnull(tool_name, '') = '' and ifnull(preset_name, '') != ''
            """
        )
    if frappe.db.has_column(doctype, "feed_rate_mm_min") and frappe.db.has_column(doctype, "feed_rate_mm_sec"):
        frappe.db.sql(
            f"""
            update `{table}`
            set feed_rate_mm_sec = round(feed_rate_mm_min / 60, 3)
            where ifnull(feed_rate_mm_sec, 0) = 0 and ifnull(feed_rate_mm_min, 0) != 0
            """
        )
    if frappe.db.has_column(doctype, "plunge_rate_mm_min") and frappe.db.has_column(doctype, "plunge_rate_mm_sec"):
        frappe.db.sql(
            f"""
            update `{table}`
            set plunge_rate_mm_sec = round(plunge_rate_mm_min / 60, 3)
            where ifnull(plunge_rate_mm_sec, 0) = 0 and ifnull(plunge_rate_mm_min, 0) != 0
            """
        )
    if frappe.db.has_column(doctype, "pass_depth_mm") and frappe.db.has_column(doctype, "stepdown_mm"):
        frappe.db.sql(
            f"""
            update `{table}`
            set stepdown_mm = pass_depth_mm
            where ifnull(stepdown_mm, 0) = 0 and ifnull(pass_depth_mm, 0) != 0
            """
        )
    for column, value in _FIXED:
        if frappe.db.has_column(doctype, column):
            frappe.db.sql(f"update `{table}` set `{column}` = %s", (value,))
    for column in ("preset_name", "feed_rate_mm_min", "plunge_rate_mm_min", "pass_depth_mm"):
        if frappe.db.has_column(doctype, column):
            frappe.db.sql_ddl(f"alter table `{table}` drop column `{column}`")
