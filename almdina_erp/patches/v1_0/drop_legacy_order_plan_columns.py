from __future__ import annotations

import frappe


RETIRED_COLUMNS = (
    "kerf_mm",
    "trim_margin_mm",
    "packing_mode",
    "cutting_machine_type",
    "optimization_time_limit_sec",
    "plan_needs_recalculation",
    "calculated_plan_input_hash",
    "calculated_plan_metadata_hash",
    "cutting_plan_json",
    "system_plan_json",
    "custom_plan_json",
    "approved_plan_source",
    "production_dxf",
)


def execute() -> None:
    """Physically retire DCO plan columns after the pre-model backfill.

    Frappe model sync does not guarantee removal of columns deleted from DocType
    JSON. This idempotent post-model patch makes the two-aggregate ownership real
    at the database layer after historical values have been migrated to Cutting
    Plan.
    """

    doctype = "Door Cutting Order"
    table = "tabDoor Cutting Order"
    if not frappe.db.table_exists(doctype):
        return

    for column in RETIRED_COLUMNS:
        if frappe.db.has_column(doctype, column):
            frappe.db.sql_ddl(f"alter table `{table}` drop column `{column}`")


__all__ = ["RETIRED_COLUMNS", "execute"]
