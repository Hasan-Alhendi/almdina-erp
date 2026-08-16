"""Backward-compatible Cutting Plan lifecycle facade.

Snapshot persistence and production-plan freezing live in
``cutting_plan_snapshot_service``. Historical whitelisted method paths remain
available here while hooks route them to the focused capability-protected
services.
"""

from __future__ import annotations

from typing import Any

import frappe

from almdina_erp.almdina_erp.services.cutting_plan_snapshot_service import (
    approve_plan,
    create_plan_from_order,
    lock_order_for_production,
)


# Historical Python callers imported the private helper from this module.
# Keep the alias while all new runtime code depends on the focused snapshot owner.
_lock_order_for_production = lock_order_for_production


@frappe.whitelist()
def submit_order_for_review(order_name: str) -> dict[str, Any]:
    """Compatibility endpoint delegated to the lifecycle permission service."""

    from almdina_erp.almdina_erp.services.order_lifecycle_permission_service import (
        submit_order_for_review as submit,
    )

    return submit(order_name)


@frappe.whitelist()
def approve_order(order_name: str) -> dict[str, Any]:
    """Compatibility endpoint delegated to the canonical approval service."""

    from almdina_erp.almdina_erp.services.order_approval_service import (
        approve_order as approve,
    )

    return approve(order_name)


@frappe.whitelist()
def send_order_to_production(order_name: str) -> dict[str, Any]:
    """Compatibility pre-dispatch validation using the dispatch capability."""

    from almdina_erp.almdina_erp.services.order_dispatch_service import (
        validate_order_for_dispatch,
    )

    return validate_order_for_dispatch(order_name)


@frappe.whitelist()
def lock_cutting_plan(
    order_name: str,
    plan_source: str = "System",
) -> dict[str, Any]:
    """Compatibility endpoint delegated to drawing-plan approval."""

    from almdina_erp.almdina_erp.services.drawing_approval_service import (
        approve_production_dxf,
    )

    return approve_production_dxf(order_name, plan_source)


@frappe.whitelist()
def reject_order(
    order_name: str,
    reason: str | None = None,
) -> dict[str, Any]:
    """Compatibility endpoint delegated to the canonical review service."""

    from almdina_erp.almdina_erp.services.order_review_service import (
        reject_order as reject,
    )

    return reject(order_name, reason)


__all__ = [
    "_lock_order_for_production",
    "approve_order",
    "approve_plan",
    "create_plan_from_order",
    "lock_cutting_plan",
    "reject_order",
    "send_order_to_production",
    "submit_order_for_review",
]
