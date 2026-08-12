from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import cint

from almdina_erp.almdina_erp.domain.orders.production_routing import (
    ProductionRoute,
    RoutingStage,
)


def _stage_definition(row: Any) -> RoutingStage:
    return RoutingStage(
        sequence=cint(row.sequence),
        stage_type=str(row.stage_type or "").strip(),
        department_label=str(getattr(row, "department_label", None) or "").strip(),
        operational_role=str(getattr(row, "operational_role", None) or "").strip(),
        is_planning_stage=bool(cint(getattr(row, "is_planning_stage", 0))),
    )


def get_route(name: str, *, require_enabled: bool = True) -> ProductionRoute:
    resolved = str(name or "").strip()
    if not resolved or not frappe.db.exists("Production Routing", resolved):
        raise ValueError(f"مسار الإنتاج {resolved or '<فارغ>'} غير موجود.")

    document = frappe.get_doc("Production Routing", resolved)
    if require_enabled and cint(document.disabled):
        raise ValueError(f"مسار الإنتاج {resolved} معطّل.")

    stages = tuple(
        _stage_definition(row)
        for row in sorted(document.stages or (), key=lambda item: cint(item.sequence))
        if cint(row.required)
    )
    return ProductionRoute(
        name=str(document.name),
        label=str(document.routing_name or document.name),
        stages=stages,
    )


def list_active_routes() -> list[ProductionRoute]:
    names = frappe.get_all(
        "Production Routing",
        filters={"disabled": 0},
        pluck="name",
        order_by="routing_name asc",
    )
    routes: list[ProductionRoute] = []
    for name in names:
        try:
            routes.append(get_route(str(name)))
        except ValueError:
            # Invalid legacy rows stay out of dispatch until an administrator
            # completes their required route metadata from master data.
            continue
    return routes


__all__ = ["get_route", "list_active_routes"]
