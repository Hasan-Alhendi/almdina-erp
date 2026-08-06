from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import cint

from almdina_erp.almdina_erp.domain.orders.lifecycle import (
    department_for_stage_type,
)
from almdina_erp.almdina_erp.domain.orders.production_routing import (
    ProductionRoute,
    RoutingStage,
)
from almdina_erp.almdina_erp.infrastructure.frappe.routing_role_codec import (
    decode_eligible_roles,
)


def _stage_definition(row: Any) -> RoutingStage:
    stage_type = str(row.stage_type or "").strip()
    return RoutingStage(
        sequence=cint(row.sequence),
        stage_type=stage_type,
        department_label=str(
            getattr(row, "department_label", None)
            or department_for_stage_type(stage_type)
            or stage_type
        ).strip(),
        eligible_roles=decode_eligible_roles(
            getattr(row, "eligible_roles_json", None),
            legacy_role=getattr(row, "operational_role", None),
        ),
    )


def get_route(name: str, *, require_enabled: bool = True) -> ProductionRoute:
    resolved = str(name or "").strip()
    if not resolved or not frappe.db.exists("Production Routing", resolved):
        raise ValueError(f"Production route {resolved or '<empty>'} does not exist.")

    document = frappe.get_doc("Production Routing", resolved)
    if require_enabled and cint(document.disabled):
        raise ValueError(f"Production route {resolved} is disabled.")

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
            # explicitly selects at least one eligible role for every stage.
            continue
    return routes


__all__ = ["get_route", "list_active_routes"]
