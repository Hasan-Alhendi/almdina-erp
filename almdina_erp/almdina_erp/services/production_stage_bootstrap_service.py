from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import cint, flt, now_datetime


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
    """Create the historical default-routing stage set for compatibility callers."""

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
        stage.department_label = route_row.department_label or route_row.stage_type
        stage.operational_role = route_row.operational_role or ""

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


__all__ = ["ensure_default_stages"]
