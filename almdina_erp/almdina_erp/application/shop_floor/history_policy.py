from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from ...domain.orders.lifecycle import normalize_order_status
from ...domain.security.authorization import Capability, normalize_capabilities


_READY_FOR_DELIVERY = "Ready for Delivery"


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


def _is_operational_ready_row(row: Mapping[str, Any] | Any) -> bool:
    """Keep only the current terminal row needed by the delivery board.

    ``get_my_archive`` historically feeds both the personal completed-history
    section and the operational "Ready for Delivery" board column. Users who
    lose history visibility must still retain the terminal row required for
    current delivery work, but no earlier completed-stage history.
    """

    order_status = normalize_order_status(_value(row, "order_status"))
    stage_name = str(_value(row, "name") or "").strip()
    current_stage_name = str(_value(row, "current_production_stage") or "").strip()
    return bool(
        order_status == _READY_FOR_DELIVERY
        and stage_name
        and stage_name == current_stage_name
    )


def visible_archive_rows(
    rows: Sequence[Mapping[str, Any] | Any] | None,
    capabilities: Iterable[str] | None,
) -> list[Any]:
    """Return history rows allowed by the actor's explicit visibility grant."""

    materialized = list(rows or ())
    if can_view_shop_floor_history(capabilities):
        return materialized
    return [row for row in materialized if _is_operational_ready_row(row)]


__all__ = [
    "can_view_shop_floor_history",
    "visible_archive_rows",
]
