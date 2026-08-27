from __future__ import annotations

from typing import Any, Callable, TypeVar

import frappe
from frappe import _

from almdina_erp.almdina_erp.application.shop_floor import history_policy
from almdina_erp.almdina_erp.application.shop_floor import order_list_query
from almdina_erp.almdina_erp.application.shop_floor import queries
from almdina_erp.almdina_erp.domain.orders.lifecycle import department_for_stage_type
from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe.authorization_gateway import (
    granted_capabilities,
)
from almdina_erp.almdina_erp.infrastructure.frappe.order_list_query_repository import (
    FrappeOrderListQueryRepository,
)
from almdina_erp.almdina_erp.infrastructure.frappe.shop_floor_query_repository import (
    FrappeShopFloorQueryRepository,
)
from almdina_erp.almdina_erp.presentation.shop_floor.data_policy import (
    sanitize_shop_floor_summary,
)


_Result = TypeVar("_Result")
_repository = FrappeShopFloorQueryRepository()
_order_list_repository = FrappeOrderListQueryRepository()


def _execute(function: Callable[..., _Result], *args: Any) -> _Result:
    try:
        return function(_repository, *args)
    except queries.ShopFloorPermissionDenied as error:
        frappe.throw(_(str(error)), frappe.PermissionError)
    except queries.ShopFloorQueryError as error:
        frappe.throw(_(str(error)))
    raise AssertionError("frappe.throw must interrupt execution")


def _current_capabilities() -> frozenset[str]:
    return granted_capabilities(user=frappe.session.user)


def _shop_floor_row_order_capabilities(row: dict[str, Any]) -> frozenset[str]:
    """Resolve an enriched stage row back to its Door Cutting Order."""

    order_name = str(row.get("door_cutting_order") or "").strip()
    if not order_name:
        return frozenset()
    return _repository.capabilities_for_order({"name": order_name})


@frappe.whitelist()
def get_shop_floor_context() -> dict[str, Any]:
    result = _execute(queries.get_shop_floor_context)
    result["can_view_history"] = history_policy.can_view_shop_floor_history(
        _current_capabilities()
    )
    return result


@frappe.whitelist()
def get_dispatch_options(order_name: str) -> dict[str, Any]:
    result = _execute(queries.get_dispatch_options, order_name)
    for path in result["paths"]:
        first_stage_type = path.pop("first_stage_type")
        path["label"] = _(path["label"])
        path["department"] = _(
            path.get("department")
            or department_for_stage_type(first_stage_type)
            or first_stage_type
        )
    return result


@frappe.whitelist()
def get_revert_targets(order_name: str) -> list[dict[str, Any]]:
    return _execute(queries.get_revert_targets, order_name)


@frappe.whitelist()
def get_current_stage_context(order_name: str) -> dict[str, Any]:
    return _execute(queries.get_current_stage_context, order_name)


@frappe.whitelist()
def get_my_inbox() -> list[dict[str, Any]]:
    rows = _execute(queries.get_my_inbox)
    return sanitize_shop_floor_summary(rows, _current_capabilities())


@frappe.whitelist()
def get_my_archive() -> list[dict[str, Any]]:
    rows = _execute(queries.get_my_archive)
    return sanitize_shop_floor_summary(rows, _current_capabilities())


@frappe.whitelist()
def get_ready_for_delivery() -> list[dict[str, Any]]:
    rows = history_policy.rows_with_order_capability(
        _execute(queries.get_ready_for_delivery),
        Capability.MARK_DELIVERED,
        capability_resolver=_shop_floor_row_order_capabilities,
    )
    return sanitize_shop_floor_summary(rows, _current_capabilities())


@frappe.whitelist()
def get_order_operational_role_flags(order_names: Any = None) -> dict[str, Any]:
    # List classification has a dedicated bulk read model. Keeping it separate
    # from the document/detail repository avoids per-row get_doc/permission/stage
    # reads while retaining Frappe's native list permission scope.
    return order_list_query.get_order_operational_role_flags(
        _order_list_repository,
        order_names,
    )


__all__ = [
    "get_dispatch_options",
    "get_current_stage_context",
    "get_my_archive",
    "get_my_inbox",
    "get_order_operational_role_flags",
    "get_ready_for_delivery",
    "get_revert_targets",
    "get_shop_floor_context",
]
