"""Initialize optimistic-concurrency revisions without rewriting CNC settings."""

from __future__ import annotations

import frappe


def execute() -> None:
    if not frappe.db.table_exists("CNC Operational File"):
        return
    if not frappe.db.has_column("CNC Operational File", "settings_revision"):
        return
    frappe.db.sql(
        """
        update `tabCNC Operational File`
        set settings_revision = 1
        where ifnull(settings_revision, 0) < 1
        """
    )
