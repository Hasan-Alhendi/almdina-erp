from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any

from ...domain.orders.lifecycle import normalize_order_status
from ...domain.orders.production_routing import ProductionRoute
from ...domain.security.authorization import Capability, normalize_capabilities


_READY_FOR_DELIVERY = "Ready for Delivery"
RouteResolver = Callable[[str], ProductionRoute]


def can_view_shop_floor_history(capabilities: Iterable[str] | None) -> bool:
    """Return whether the actor may see completed Shop Floor history.

    This capability is deliberately visibility-only. Shop Floor entry and order
    scope are enforced independently by the existing query authorization path.
    """

    return Capability.VIEW_SHOP_FLOOR_HISTORY in normalize_capabilities(capabilities)


def _value(row: Mapping[str, Any] | Any, fieldname: str) -> Any:
    if isinstance(row, Mapping):
        return row.get(fieldname)
    return getattr(row, fieldname, None)


def _is_terminal_route_stage(
    row: Mapping[str, Any] | Any,
    route_resolver: RouteResolver | None,
) -> bool:
    """Fail closed unless the row belongs to the final stage of its route."""

    if route_resolver is None:
        return False
    route_name = str(_value(row, "production_path") or "").strip()
    stage_type = str(_value(row, "stage_type") or "").strip()
    if not route_name or not stage_type:
        return False
    try:
        route = route_resolver(route_name)
        return route.next_stage(stage_type) is None
    except (ValueError, AttributeError):
        return False


def _is_operational_ready_row(
    row: Mapping[str, Any] | Any,
    route_resolver: RouteResolver | None,
) -> bool:
    """Keep only the terminal row required by the Ready-for-Delivery board.

    Completing the final production stage clears ``current_production_stage``.
    Therefore terminality must come from the canonical Production Routing, not
    from the order's current-stage pointer. This preserves delivery work without
    exposing earlier completed-stage history.
    """

    return bool(
        normalize_order_status(_value(row, "order_status")) == _READY_FOR_DELIVERY
        and _is_terminal_route_stage(row, route_resolver)
    )


def visible_archive_rows(
    rows: Sequence[Mapping[str, Any] | Any] | None,
    capabilities: Iterable[str] | None,
    *,
    route_resolver: RouteResolver | None = None,
) -> list[Any]:
    """Return history rows allowed by the actor's explicit visibility grant."""

    materialized = list(rows or ())
    if can_view_shop_floor_history(capabilities):
        return materialized
    return [
        row
        for row in materialized
        if _is_operational_ready_row(row, route_resolver)
    ]


__all__ = [
    "RouteResolver",
    "can_view_shop_floor_history",
    "visible_archive_rows",
]
