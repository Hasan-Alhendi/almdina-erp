from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any

from ...domain.orders.lifecycle import normalize_order_status
from ...domain.orders.production_routing import ProductionRoute
from ...domain.security.authorization import Capability, normalize_capabilities


_READY_FOR_DELIVERY = "Ready for Delivery"
RouteResolver = Callable[[str], ProductionRoute]
OrderCapabilityResolver = Callable[[Mapping[str, Any] | Any], Iterable[str] | None]


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
    except (KeyError, ValueError, AttributeError):
        return False


def _is_operational_ready_row(
    row: Mapping[str, Any] | Any,
    route_resolver: RouteResolver | None,
) -> bool:
    """Return whether the row is the terminal operational delivery row."""

    return bool(
        normalize_order_status(_value(row, "order_status")) == _READY_FOR_DELIVERY
        and _is_terminal_route_stage(row, route_resolver)
    )


def ready_for_delivery_rows(
    rows: Sequence[Mapping[str, Any] | Any] | None,
    *,
    route_resolver: RouteResolver | None = None,
) -> list[Any]:
    """Return only terminal rows needed by the delivery-ready board.

    Ready-for-delivery is operational data, not completed-history data. Keeping
    this policy separate prevents the history permission from becoming a hidden
    dependency of the delivery workflow.
    """

    return [
        row
        for row in list(rows or ())
        if _is_operational_ready_row(row, route_resolver)
    ]


def rows_with_order_capability(
    rows: Sequence[Mapping[str, Any] | Any] | None,
    capability: str,
    *,
    capability_resolver: OrderCapabilityResolver,
) -> list[Any]:
    """Keep only rows whose underlying order grants ``capability``.

    The resolver belongs to the infrastructure adapter so native document scope
    (including Frappe User Permissions) remains authoritative. This policy is
    intentionally fail-closed when the resolver returns no capabilities.
    """

    return [
        row
        for row in list(rows or ())
        if capability in normalize_capabilities(capability_resolver(row))
    ]


def visible_archive_rows(
    rows: Sequence[Mapping[str, Any] | Any] | None,
    capabilities: Iterable[str] | None,
) -> list[Any]:
    """Return true completed history allowed by the explicit history grant.

    The function intentionally excludes ``Ready for Delivery`` because those
    rows belong to the operational delivery query, not the history surface.
    """

    if not can_view_shop_floor_history(capabilities):
        return []
    return [
        row
        for row in list(rows or ())
        if normalize_order_status(_value(row, "order_status")) != _READY_FOR_DELIVERY
    ]


__all__ = [
    "OrderCapabilityResolver",
    "RouteResolver",
    "can_view_shop_floor_history",
    "ready_for_delivery_rows",
    "rows_with_order_capability",
    "visible_archive_rows",
]
