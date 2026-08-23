from __future__ import annotations

from typing import Any

import frappe

from almdina_erp.almdina_erp.application.orders.plan_snapshot_security import (
    sanitize_plan_snapshot_json,
)


_BATCH_SIZE = 200
_ORDER_PLAN_FIELDS = (
    "cutting_plan_json",
    "system_plan_json",
    "custom_plan_json",
)


def _existing_fields(doctype: str, fields: tuple[str, ...]) -> tuple[str, ...]:
    if not frappe.db.table_exists(doctype):
        return ()
    columns = set(frappe.db.get_table_columns(doctype))
    return tuple(fieldname for fieldname in fields if fieldname in columns)


def _sanitize_rows(doctype: str, fields: tuple[str, ...]) -> None:
    available_fields = _existing_fields(doctype, fields)
    if not available_fields:
        return

    offset = 0
    while True:
        rows = frappe.get_all(
            doctype,
            fields=["name", *available_fields],
            order_by="name asc",
            limit_start=offset,
            limit_page_length=_BATCH_SIZE,
        )
        if not rows:
            return

        for row in rows:
            updates: dict[str, Any] = {}
            for fieldname in available_fields:
                raw = row.get(fieldname)
                if raw in (None, ""):
                    continue
                sanitized = sanitize_plan_snapshot_json(raw)
                if sanitized != raw:
                    updates[fieldname] = sanitized

            if updates:
                frappe.db.set_value(
                    doctype,
                    row.name,
                    updates,
                    update_modified=False,
                )

        offset += len(rows)


def execute() -> None:
    """Remove financial metadata from persisted operational plan JSON safely."""

    _sanitize_rows("Door Cutting Order", _ORDER_PLAN_FIELDS)
    _sanitize_rows("Cutting Plan", ("snapshot_json",))
