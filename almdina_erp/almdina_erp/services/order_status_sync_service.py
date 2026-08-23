from __future__ import annotations

from typing import Any

import frappe

from almdina_erp.almdina_erp.domain.orders.lifecycle import (
    SHOP_FLOOR_ORDER_STATUSES,
    StageState,
    derive_order_status,
)


def _base_stages(order_name: str) -> list[Any]:
    stages = frappe.get_all(
        "Production Stage",
        filters={"door_cutting_order": order_name},
        fields=["name", "stage_type", "status", "sequence", "piece_label"],
        order_by="sequence asc",
    )
    return [row for row in stages if not (row.piece_label or "")]


def sync_order_status(order_name: str) -> str:
    """Derive order status from the canonical current stage and replacements."""

    open_replacements = (
        frappe.db.count(
            "Replacement Piece",
            filters={
                "door_cutting_order": order_name,
                "status": ["not in", ["Completed", "Cancelled"]],
            },
        )
        if frappe.db.exists("DocType", "Replacement Piece")
        else 0
    )
    if open_replacements:
        status = derive_order_status(
            current_status=None,
            production_path=None,
            current_stage=None,
            stages=(),
            has_open_replacements=True,
        )
        frappe.db.set_value(
            "Door Cutting Order",
            order_name,
            "status",
            status,
            update_modified=True,
        )
        return status

    current = frappe.db.get_value(
        "Door Cutting Order",
        order_name,
        ["status", "production_path", "current_production_stage"],
        as_dict=True,
    )
    if current and current.status in {"Ready for Delivery", "Delivered"}:
        return current.status

    if current and current.production_path:
        if current.current_production_stage:
            stage = frappe.db.get_value(
                "Production Stage",
                current.current_production_stage,
                ["stage_type", "status"],
                as_dict=True,
            )
            if stage and stage.status != "Cancelled":
                mapped = SHOP_FLOOR_ORDER_STATUSES.get(stage.stage_type)
                if mapped:
                    frappe.db.set_value(
                        "Door Cutting Order",
                        order_name,
                        "status",
                        mapped,
                        update_modified=True,
                    )
                    return mapped
        if current.status and current.status.startswith("At "):
            return current.status

    stages = _base_stages(order_name)
    if not stages:
        return (current.status if current else None) or "Draft"

    status = derive_order_status(
        current_status=current.status if current else None,
        production_path=current.production_path if current else None,
        current_stage=None,
        stages=(StageState(row.stage_type, row.status) for row in stages),
        has_open_replacements=False,
    )
    frappe.db.set_value(
        "Door Cutting Order",
        order_name,
        "status",
        status,
        update_modified=True,
    )
    return status


__all__ = ["sync_order_status"]
