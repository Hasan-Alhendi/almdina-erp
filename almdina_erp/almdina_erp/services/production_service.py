from __future__ import annotations

from typing import Any

import frappe

from almdina_erp.almdina_erp.domain.orders.lifecycle import (
    SHOP_FLOOR_ORDER_STATUSES,
    StageState,
    derive_order_status,
)


def ensure_default_stages(
    order_name: str,
    approved_by: str | None = None,
) -> list[str]:
    """Return existing route stages without auto-dispatching an approved order.

    This historical function used to create every configured stage at approval
    time without selecting an eligible worker. The current workflow separates
    approval from dispatch: a supervisor explicitly chooses the route and first
    assignee through the capability-protected dispatch command. Keeping this
    read-only facade avoids breaking old internal callers while preventing
    hidden assignments, invented workers, and duplicate route stages.
    """

    del approved_by
    rows = frappe.get_all(
        "Production Stage",
        filters={"door_cutting_order": order_name},
        fields=["name", "piece_label", "sequence"],
        order_by="sequence asc, name asc",
    )
    return [str(row.name) for row in rows if not str(row.piece_label or "").strip()]


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


@frappe.whitelist()
def start_stage(
    stage_name: str,
    assigned_to: str | None = None,
) -> dict[str, Any]:
    from almdina_erp.almdina_erp.services.legacy_endpoint_service import (
        start_legacy_stage,
    )

    return start_legacy_stage(stage_name, assigned_to)


@frappe.whitelist()
def finish_stage(
    stage_name: str,
    completed_qty: int | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    from almdina_erp.almdina_erp.services.legacy_endpoint_service import (
        finish_legacy_stage,
    )

    return finish_legacy_stage(stage_name, completed_qty, notes)


@frappe.whitelist()
def pause_stage(stage_name: str, reason: str | None = None) -> dict[str, Any]:
    del stage_name, reason
    from almdina_erp.almdina_erp.services.legacy_endpoint_service import (
        retired_product_endpoint,
    )

    return retired_product_endpoint()


@frappe.whitelist()
def resume_stage(stage_name: str) -> dict[str, Any]:
    del stage_name
    from almdina_erp.almdina_erp.services.legacy_endpoint_service import (
        retired_product_endpoint,
    )

    return retired_product_endpoint()


__all__ = [
    "ensure_default_stages",
    "finish_stage",
    "pause_stage",
    "resume_stage",
    "start_stage",
    "sync_order_status",
]
