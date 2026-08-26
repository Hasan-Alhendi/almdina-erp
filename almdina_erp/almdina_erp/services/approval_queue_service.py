from __future__ import annotations

from typing import NoReturn

import frappe

from almdina_erp.almdina_erp.services.legacy_endpoint_service import (
    reject_retired_approval_workflow,
)


@frappe.whitelist()
def get_approval_queue_context() -> NoReturn:
    reject_retired_approval_workflow()


@frappe.whitelist()
def get_pending_review_orders(limit: int = 100) -> NoReturn:
    reject_retired_approval_workflow(limit)


@frappe.whitelist()
def approve_order_safely(order_name: str) -> NoReturn:
    reject_retired_approval_workflow(order_name)


@frappe.whitelist()
def reject_order_safely(order_name: str, reason: str) -> NoReturn:
    reject_retired_approval_workflow(order_name, reason)


__all__ = [
    "approve_order_safely",
    "get_approval_queue_context",
    "get_pending_review_orders",
    "reject_order_safely",
]
