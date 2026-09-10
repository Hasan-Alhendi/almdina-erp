from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import frappe
from frappe.utils import cint

from almdina_erp.almdina_erp.application.factory.production_stage_definition_management import (
    ProductionStageDefinitionSnapshot,
)
from almdina_erp.almdina_erp.domain.orders.production_routing import (
    ProductionRoute,
    RoutingStage,
)
from almdina_erp.almdina_erp.infrastructure.frappe.production_stage_definition_repository import (
    FrappeProductionStageDefinitionRepository,
)


_REQUEST_CACHE_KEY = "almdina_production_route_cache"


def _stage_definition(
    row: Any,
    definitions: Mapping[str, ProductionStageDefinitionSnapshot],
) -> RoutingStage:
    definition_name = str(row.stage_definition or "").strip()
    definition = definitions.get(definition_name)
    if definition is None:
        raise ValueError(
            f"تعريف مرحلة الإنتاج {definition_name or '<فارغ>'} غير موجود."
        )
    return RoutingStage(
        sequence=cint(row.sequence),
        stage_type=definition.stage_code,
        department_label=definition.stage_label,
        operational_role=str(getattr(row, "operational_role", None) or "").strip(),
        is_planning_stage=bool(cint(getattr(row, "is_planning_stage", 0))),
    )


def _request_cache() -> dict[str, tuple[ProductionRoute, bool]]:
    """Return a request-local immutable route projection cache."""

    cache = getattr(frappe.local, _REQUEST_CACHE_KEY, None)
    if cache is None:
        cache = {}
        setattr(frappe.local, _REQUEST_CACHE_KEY, cache)
    return cache


def _route_projection(document: Any) -> ProductionRoute:
    required_rows = [row for row in document.stages or () if cint(row.required)]
    definitions = FrappeProductionStageDefinitionRepository().get_definitions(
        [str(row.stage_definition or "") for row in required_rows]
    )
    stages = tuple(
        _stage_definition(row, definitions)
        for row in sorted(required_rows, key=lambda item: cint(item.sequence))
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
            # Invalid configuration stays out of dispatch until an administrator
            # completes its required stage-library metadata.
            continue
    return routes


__all__ = ["get_route", "list_active_routes"]
