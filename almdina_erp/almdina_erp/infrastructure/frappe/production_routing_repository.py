from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import cint

from almdina_erp.almdina_erp.domain.orders.production_routing import (
    ProductionRoute,
    RoutingStage,
)


_REQUEST_CACHE_KEY = "almdina_production_route_cache"
_STAGE_CACHE_KEY = "almdina_production_workflow_stage_cache"


def _request_cache() -> dict[str, tuple[ProductionRoute, bool]]:
    cache = getattr(frappe.local, _REQUEST_CACHE_KEY, None)
    if cache is None:
        cache = {}
        setattr(frappe.local, _REQUEST_CACHE_KEY, cache)
    return cache


def _stage_cache() -> dict[str, Any]:
    cache = getattr(frappe.local, _STAGE_CACHE_KEY, None)
    if cache is None:
        cache = {}
        setattr(frappe.local, _STAGE_CACHE_KEY, cache)
    return cache


def _workflow_stage_name(row: Any) -> str:
    return str(getattr(row, "workflow_stage", None) or "").strip()


def _workflow_stage_definitions(rows: Any) -> dict[str, Any]:
    names = sorted(
        {
            _workflow_stage_name(row)
            for row in rows
            if cint(row.required) and _workflow_stage_name(row)
        }
    )
    cache = _stage_cache()
    missing = [name for name in names if name not in cache]
    if missing:
        found = frappe.get_all(
            "Production Workflow Stage",
            filters={"name": ["in", missing]},
            fields=["name", "stage_code", "stage_label", "disabled"],
        )
        for item in found:
            cache[str(item.name)] = item
        for name in missing:
            cache.setdefault(name, None)
    return {name: cache.get(name) for name in names}


def _stage_definition(row: Any, definition: Any) -> RoutingStage:
    workflow_stage = _workflow_stage_name(row)
    if workflow_stage:
        if not definition:
            raise ValueError("مسار الإنتاج يحتوي على مرحلة غير معرفة في دليل مراحل الإنتاج.")
        if cint(definition.disabled):
            raise ValueError(f"مرحلة الإنتاج {definition.stage_label or definition.stage_code} معطّلة.")
        stage_type = str(definition.stage_code or "").strip()
        department_label = str(definition.stage_label or "").strip()
    else:
        # Transitional read-only fallback for pre-migration rows and historical
        # snapshots. New/edited rows are validated to require workflow_stage.
        stage_type = str(getattr(row, "stage_type", None) or "").strip()
        department_label = str(getattr(row, "department_label", None) or stage_type).strip()
        if not stage_type:
            raise ValueError("مسار الإنتاج يحتوي على مرحلة غير معرفة في دليل مراحل الإنتاج.")

    return RoutingStage(
        sequence=cint(row.sequence),
        stage_type=stage_type,
        department_label=department_label,
        operational_role=str(getattr(row, "operational_role", None) or "").strip(),
        is_planning_stage=bool(cint(getattr(row, "is_planning_stage", 0))),
    )


def _route_projection(document: Any) -> ProductionRoute:
    rows = [
        row
        for row in sorted(document.stages or (), key=lambda item: cint(item.sequence))
        if cint(row.required)
    ]
    definitions = _workflow_stage_definitions(rows)
    stages = tuple(
        _stage_definition(row, definitions.get(_workflow_stage_name(row)))
        for row in rows
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
            continue
    return routes


__all__ = ["get_route", "list_active_routes"]
