from __future__ import annotations

import frappe


# This historical patch used to create fixed roles and two fixed routes. New
# installations must start empty and let administrators build their own roles
# and routes. Existing sites retain every record previously created by older
# releases; this patch now only normalizes blank display labels safely.


def _backfill_department_labels(doctype: str) -> None:
    if not frappe.db.exists("DocType", doctype):
        return
    rows = frappe.get_all(
        doctype,
        fields=["name", "stage_type", "department_label"],
    )
    for row in rows:
        stage_type = str(row.stage_type or "").strip()
        if stage_type and not str(row.department_label or "").strip():
            frappe.db.set_value(
                doctype,
                row.name,
                "department_label",
                stage_type,
                update_modified=False,
            )


def execute() -> None:
    """Preserve existing route data without creating roles or routes."""

    _backfill_department_labels("Production Routing Stage")
    _backfill_department_labels("Production Stage")


__all__ = ["execute"]
