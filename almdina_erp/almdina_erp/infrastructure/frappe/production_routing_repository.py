from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import cint

from almdina_erp.almdina_erp.domain.orders.production_routing import (
    ProductionRoute,
    RoutingStage,
)


_REQUEST_CACHE_KEY = "almdina_production_route_cache"


def _stage_definition(row: Any) -> RoutingStage:
    return RoutingStage(
        sequence=cint(row.sequence),
        stage_type=str(row.stage_type or "").strip(),
        department_label=str(getattr(row, "department_label", None) or "").strip(),
        operational_role=str(getattr(row, "operational_role", None) or "").strip(),
        is_planning_stage=bool(cint(getattr(row, "is_planning_stage", 0))),
    )


def _request_cache() -> dict[str, tuple[ProductionRoute, bool]]:
    """Return a request-local immutable route projection cache.

    `frappe.local` is scoped to the current request/job context, so this cache
    never survives into a later HTTP request. That gives repeated routing reads
    within one application use case a cheap fast path without cross-request
    invalidation or stale configuration risk.
    """

    cache = getattr(frappe.local, _REQUEST_CACHE_KEY, None)
    if cache is None:
        cache = {}
        setattr(frappe.local, _REQUEST_CACHE_KEY, cache)
    return cache


def _route_projection(document: Any) -> ProductionRoute:
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


def _load_route(resolved: str) -> tuple[ProductionRoute, bool]:
    cache = _request_cache()
    cached = cache.get(resolved)
    if cached is not None:
        return cached

    if not frappe.db.exists("Production Routing", resolved):
        raise ValueError(f"مسار الإنتاج {resolved or '<فارغ>'} غير موجود.")

    document = frappe.get_doc("Production Routing", resolved)
    cached = (_route_projection(document), bool(cint(document.disabled)))
    cache[resolved] = cached
    return cached


def get_route(name: str, *, require_enabled: bool = True) -> ProductionRoute:
    resolved = str(name or "").strip()
    if not resolved:
        raise ValueError("مسار الإنتاج <فارغ> غير موجود.")

    route, disabled = _load_route(resolved)
    if require_enabled and disabled:
        raise ValueError(f"مسار الإنتاج {resolved} معطّل.")
    return route


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
