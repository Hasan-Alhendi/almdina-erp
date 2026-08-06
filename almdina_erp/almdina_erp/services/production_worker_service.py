from __future__ import annotations

from typing import Any

import frappe
from frappe import _

from almdina_erp.almdina_erp.application.shop_floor import commands
from almdina_erp.almdina_erp.infrastructure.frappe.shop_floor_command_repository import (
    FrappeShopFloorCommandRepository,
)


_repository = FrappeShopFloorCommandRepository()


@frappe.whitelist()
def get_reassignment_workers(stage_name: str) -> list[dict[str, Any]]:
    try:
        return commands.get_reassignment_workers(_repository, stage_name)
    except commands.ShopFloorPermissionDenied as error:
        frappe.throw(_(str(error)), frappe.PermissionError)
    except commands.ShopFloorCommandError as error:
        frappe.throw(_(str(error)))
    raise AssertionError("frappe.throw must interrupt execution")


__all__ = ["get_reassignment_workers"]
