from __future__ import annotations

import json
from typing import Any

import frappe


_PIECE_TABLES = ("Door Cutting Order Detail", "Cutting Plan Piece")
_SNAPSHOT_FIELDS = (
    ("Cutting Plan", "snapshot_json"),
    ("Door Cutting Order", "cutting_plan_json"),
)


def normalize_extra_piece_types(value: Any) -> tuple[Any, bool]:
    """Return a copy with legacy piece types normalized and all other data intact."""

    if isinstance(value, dict):
        changed = False
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            if key == "piece_type" and item == "Extra":
                normalized[key] = "Regular"
                changed = True
                continue
            normalized_item, item_changed = normalize_extra_piece_types(item)
            normalized[key] = normalized_item
            changed = changed or item_changed
        return normalized, changed
    if isinstance(value, list):
        changed = False
        normalized_items: list[Any] = []
        for item in value:
            normalized_item, item_changed = normalize_extra_piece_types(item)
            normalized_items.append(normalized_item)
            changed = changed or item_changed
        return normalized_items, changed
    return value, False


def _migrate_snapshot_field(doctype: str, fieldname: str) -> None:
    if not frappe.db.has_column(doctype, fieldname):
        return
    for row in frappe.get_all(
        doctype,
        filters={fieldname: ["is", "set"]},
        fields=["name", fieldname],
    ):
        raw = row.get(fieldname)
        if not raw:
            continue
        try:
            payload = json.loads(raw) if isinstance(raw, str) else raw
        except (TypeError, ValueError):
            continue
        normalized, changed = normalize_extra_piece_types(payload)
        if not changed:
            continue
        frappe.db.set_value(
            doctype,
            row.name,
            fieldname,
            json.dumps(normalized, ensure_ascii=False, separators=(",", ":")),
            update_modified=False,
        )


def execute() -> None:
    """Map the retired Extra type to Regular without touching add-on history."""

    for doctype in _PIECE_TABLES:
        if not frappe.db.has_column(doctype, "piece_type"):
            continue
        frappe.db.sql(
            f"""
            update `tab{doctype}`
               set piece_type = 'Regular'
             where piece_type = 'Extra'
            """
        )
    for doctype, fieldname in _SNAPSHOT_FIELDS:
        _migrate_snapshot_field(doctype, fieldname)


__all__ = ["execute", "normalize_extra_piece_types"]
