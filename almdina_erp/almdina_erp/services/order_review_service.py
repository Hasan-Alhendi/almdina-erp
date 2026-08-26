from __future__ import annotations

from typing import NoReturn

import frappe

from almdina_erp.almdina_erp.services.legacy_endpoint_service import (
    reject_retired_approval_workflow,
)


@frappe.whitelist()
def reject_order(order_name: str, reason: str | None = None) -> NoReturn:
    reject_retired_approval_workflow(order_name, reason)


__all__ = ["reject_order"]
