from __future__ import annotations

import frappe


OBSOLETE_COLUMNS = (
    "board_material",
    "board_color",
    "board_thickness_mm",
)


def execute() -> None:
    """Remove columns retired by the free-text board input model.

    The patch is idempotent and safe for new sites where the columns were never
    created. Door Cutting Order data was intentionally cleared before this schema
    cleanup, so no legacy values need migration.
    """

    doctype = "Door Cutting Order"
    table = "tabDoor Cutting Order"
    if not frappe.db.table_exists(doctype):
        return

    for column in OBSOLETE_COLUMNS:
        if frappe.db.has_column(doctype, column):
            frappe.db.sql_ddl(f"alter table `{table}` drop column `{column}`")
