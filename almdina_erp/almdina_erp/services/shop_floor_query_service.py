from __future__ import annotations

from typing import Any, Callable, TypeVar

import frappe
from frappe import _

from almdina_erp.almdina_erp.application.shop_floor import queries
from almdina_erp.almdina_erp.infrastructure.frappe import shop_floor_authorization
from almdina_erp.almdina_erp.infrastructure.frappe.shop_floor_query_repository import (
    FrappeShopFloorQueryRepository,
)
from almdina_erp.almdina_erp.presentation.shop_floor.presenters import (
    present_order_detail,
)


_Result = TypeVar("_Result")
_repository = FrappeShopFloorQueryRepository()


def _execute(function: Callable[..., _Result], *args: Any) -> _Result:
    try:
        return function(_repository, *args)
    except queries.ShopFloorPermissionDenied as error:
        frappe.throw(_(str(error)), frappe.PermissionError)
    except queries.ShopFloorQueryError as error:
        frappe.throw(_(str(error)))
    raise AssertionError("frappe.throw must interrupt execution")


@frappe.whitelist()
def get_dispatch_options(order_name: str) -> dict[str, Any]:
    result = _execute(queries.get_dispatch_options, order_name)
    for path in result["paths"]:
        first_stage_type = path.pop("first_stage_type")
        path["label"] = _(path["label"])
        path["department"] = shop_floor_authorization.STAGE_ROLE_BY_TYPE[
            first_stage_type
        ]
    return result


@frappe.whitelist()
def get_revert_targets(order_name: str) -> list[dict[str, Any]]:
    return _execute(queries.get_revert_targets, order_name)


@frappe.whitelist()
def get_my_inbox() -> list[dict[str, Any]]:
    return _execute(queries.get_my_inbox)


@frappe.whitelist()
def get_my_archive() -> list[dict[str, Any]]:
    return _execute(queries.get_my_archive)


@frappe.whitelist()
def get_order_shop_floor_detail(order_name: str) -> dict[str, Any]:
    result = _execute(queries.get_order_detail, order_name)
    return present_order_detail(
        result,
        translate=_,
        escape=lambda value: frappe.utils.escape_html(str(value)),
        dumps=frappe.as_json,
    )


__all__ = [
    "get_dispatch_options",
    "get_my_archive",
    "get_my_inbox",
    "get_order_shop_floor_detail",
    "get_revert_targets",
]
