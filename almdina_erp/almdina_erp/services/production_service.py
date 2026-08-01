from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import cint, flt, now_datetime

from almdina_erp.almdina_erp.domain.orders.lifecycle import (
    SHOP_FLOOR_ORDER_STATUSES,
    StageState,
    derive_order_status,
)


def _log_event(
    stage: Any,
    event_type: str,
    details: dict[str, Any] | None = None,
    actor: str | None = None,
) -> None:
    event = frappe.new_doc("Production Stage Event")
    event.door_cutting_order = stage.door_cutting_order
    event.production_stage = stage.name
    event.stage_type = stage.stage_type
    event.event_type = event_type
    event.event_time = now_datetime()
    event.actor = actor or frappe.session.user
    event.details_json = frappe.as_json(details or {})
    event.insert(ignore_permissions=True)


def _get_routing() -> Any:
    settings = frappe.get_single("Almdina ERP Settings")
    routing_name = settings.default_production_routing
    if not routing_name:
        frappe.throw(_("Set Default Production Routing in Almdina ERP Settings."))
    routing = frappe.get_doc("Production Routing", routing_name)
    if routing.disabled:
        frappe.throw(_("Production Routing {0} is disabled.").format(routing_name))
    return routing


def _stage_is_applicable(stage_type: str, order: Any) -> bool:
    if stage_type == "Edge Banding":
        return flt(order.total_edge_meters) > 0
    return True


def _required_piece_qty(order_name: str) -> int:
    rows = frappe.get_all(
        "Door Cutting Order Detail",
        filters={
            "parent": order_name,
            "parenttype": "Door Cutting Order",
        },
        fields=["qty"],
    )
    return sum(cint(row.qty) for row in rows)


def ensure_default_stages(
    order_name: str,
    approved_by: str | None = None,
) -> list[str]:
    """Compatibility stage creation used only by approved internal flows."""

    existing = frappe.get_all(
        "Production Stage",
        filters={"door_cutting_order": order_name},
        order_by="sequence asc",
        pluck="name",
    )
    base_existing = [
        name
        for name in existing
        if not (
            frappe.db.get_value("Production Stage", name, "piece_label") or ""
        )
    ]
    if base_existing:
        return base_existing

    order = frappe.get_doc("Door Cutting Order", order_name)
    routing = _get_routing()
    created: list[str] = []
    now = now_datetime()
    actor = approved_by or frappe.session.user

    for route_row in sorted(
        routing.stages or [],
        key=lambda row: cint(row.sequence),
    ):
        if not cint(route_row.required):
            continue

        applicable = _stage_is_applicable(route_row.stage_type, order)
        stage = frappe.new_doc("Production Stage")
        stage.door_cutting_order = order_name
        stage.sequence = cint(route_row.sequence)
        stage.stage_type = route_row.stage_type

        auto_completed = route_row.stage_type == "Review / Preparation" or (
            not applicable and cint(route_row.auto_complete_if_not_applicable)
        )
        if auto_completed:
            stage.status = "Completed"
            stage.assigned_to = actor
            stage.started_by = actor
            stage.start_time = now
            stage.finished_by = actor
            stage.finish_time = now
            stage.actual_working_seconds = 0
            stage.completed_qty = (
                _required_piece_qty(order_name) if applicable else 0
            )
            if not applicable:
                stage.notes = _(
                    "Automatically completed because this stage is not "
                    "applicable to the order."
                )
        else:
            stage.status = "Pending"

        stage.insert(ignore_permissions=True)
        _log_event(
            stage,
            "Created",
            {
                "routing": routing.name,
                "sequence": stage.sequence,
                "applicable": applicable,
                "initial_status": stage.status,
            },
            actor=actor,
        )
        if auto_completed:
            _log_event(
                stage,
                "Finish",
                {"automatic": True, "applicable": applicable},
                actor=actor,
            )
        created.append(stage.name)

    return created


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
