from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import cint, now_datetime

from almdina_erp.almdina_erp.infrastructure.frappe.production_routing_repository import get_route


def _log_event(stage: Any, event_type: str, details: dict[str, Any] | None = None, actor: str | None = None) -> None:
    event = frappe.new_doc("Production Stage Event")
    event.door_cutting_order = stage.door_cutting_order
    event.production_stage = stage.name
    event.stage_type = stage.stage_type
    event.event_type = event_type
    event.event_time = now_datetime()
    event.actor = actor or frappe.session.user
    event.details_json = frappe.as_json(details or {})
    event.insert(ignore_permissions=True)


def _get_routing_name() -> str:
    settings = frappe.get_single("Almdina ERP Settings")
    routing_name = str(settings.default_production_routing or "").strip()
    if not routing_name:
        frappe.throw(_("Set Default Production Routing in Almdina ERP Settings."))
    return routing_name


def ensure_default_stages(order_name: str, approved_by: str | None = None) -> list[str]:
    """Compatibility bootstrap backed exclusively by configured route metadata."""
    existing = frappe.get_all(
        "Production Stage",
        filters={"door_cutting_order": order_name},
        fields=["name", "piece_label"],
        order_by="sequence asc",
    )
    base_existing = [str(row.name) for row in existing if not str(row.piece_label or "")]
    if base_existing:
        return base_existing

    routing_name = _get_routing_name()
    route = get_route(routing_name)
    actor = approved_by or frappe.session.user
    created: list[str] = []
    for definition in route.stages:
        stage = frappe.new_doc("Production Stage")
        stage.door_cutting_order = order_name
        stage.sequence = cint(definition.sequence)
        stage.stage_type = definition.stage_type
        stage.department_label = definition.department_label
        stage.operational_role = definition.operational_role
        stage.status = "Pending"
        stage.insert(ignore_permissions=True)
        _log_event(stage, "Created", {"routing": routing_name, "sequence": stage.sequence, "initial_status": stage.status}, actor=actor)
        created.append(stage.name)
    return created


__all__ = ["ensure_default_stages"]
