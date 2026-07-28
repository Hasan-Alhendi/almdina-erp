from __future__ import annotations

from typing import Any

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


_repository = FrappeShopFloorQueryRepository()


def _permission_error(error: queries.ShopFloorPermissionDenied) -> None:
    frappe.throw(_(str(error)), frappe.PermissionError)


@frappe.whitelist()
def get_dispatch_options() -> dict[str, Any]:
    shop_floor_authorization.require_roles(*shop_floor_authorization.DISPATCH_ROLES)
    result = queries.get_dispatch_options(_repository)
    for path in result["paths"]:
        first_stage_type = path.pop("first_stage_type")
        path["label"] = _(path["label"])
        path["first_role"] = shop_floor_authorization.STAGE_ROLE_BY_TYPE[
            first_stage_type
        ]
    return result


@frappe.whitelist()
def get_revert_targets(order_name: str) -> list[dict[str, Any]]:
    shop_floor_authorization.require_roles(*shop_floor_authorization.ADMIN_ROLES)
    return queries.get_revert_targets(_repository, order_name)


@frappe.whitelist()
def get_my_inbox() -> list[dict[str, Any]]:
    try:
        return queries.get_my_inbox(_repository)
    except queries.ShopFloorPermissionDenied as error:
        _permission_error(error)
    raise AssertionError("frappe.throw must interrupt execution")


@frappe.whitelist()
def get_my_archive() -> list[dict[str, Any]]:
    try:
        return queries.get_my_archive(_repository)
    except queries.ShopFloorPermissionDenied as error:
        _permission_error(error)
    raise AssertionError("frappe.throw must interrupt execution")


@frappe.whitelist()
def get_order_shop_floor_detail(order_name: str) -> dict[str, Any]:
    try:
        result = queries.get_order_detail(_repository, order_name)
    except queries.ShopFloorPermissionDenied as error:
        _permission_error(error)
        raise AssertionError("frappe.throw must interrupt execution")
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
