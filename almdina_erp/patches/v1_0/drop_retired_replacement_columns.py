from __future__ import annotations

import frappe


RETIRED_COLUMNS = (
    ("Door Cutting Order", "internal_loss_cost_usd"),
    ("Door Cutting Costing", "internal_loss_cost_usd"),
    ("Cutting Plan", "replacement_piece"),
    ("Material Reservation", "replacement_piece"),
)


def execute() -> None:
    """Drop columns left behind after replacement and incident removal.

    Frappe model sync does not guarantee removal of columns deleted from DocType
    JSON. The data rewrite already ran in pre_model_sync, so this post-model
    patch only drops empty schema. A second migrate finds the columns gone.
    """

    for doctype, column in RETIRED_COLUMNS:
        table = f"tab{doctype}"
        if not frappe.db.table_exists(doctype):
            continue
        if frappe.db.has_column(doctype, column):
            frappe.db.sql_ddl(f"alter table `{table}` drop column `{column}`")
