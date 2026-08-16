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


def _sanitize_rows(doctype: str, fields: tuple[str, ...]) -> None:
    offset = 0
    while True:
        rows = frappe.get_all(
            doctype,
            fields=["name", *fields],
            order_by="name asc",
            limit_start=offset,
            limit_page_length=_BATCH_SIZE,
        )
        if not rows:
            return

        for row in rows:
            updates: dict[str, Any] = {}
            for fieldname in fields:
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
    """Remove financial metadata from every persisted operational plan JSON."""

    _sanitize_rows("Door Cutting Order", _ORDER_PLAN_FIELDS)
    _sanitize_rows("Cutting Plan", ("snapshot_json",))
