"""Backward-compatible Cutting Plan lifecycle facade.

Snapshot persistence and production-plan freezing live in
``cutting_plan_snapshot_service``. Historical whitelisted method paths and
Python-callable names remain available here as thin delegates.
"""

from __future__ import annotations

from typing import Any

import frappe

from almdina_erp.almdina_erp.services import cutting_plan_snapshot_service as _snapshot


def create_plan_from_order(
    order: Any,
    snapshot_override: dict[str, Any] | None = None,
    *,
    plan_kind: str = "Order",
) -> Any:
    """Compatibility delegate to the focused snapshot persistence owner."""

    return _snapshot.create_plan_from_order(
        order,
        snapshot_override,
        plan_kind=plan_kind,
    )


def approve_plan(plan: Any) -> Any:
    """Compatibility delegate to the focused snapshot persistence owner."""

    return _snapshot.approve_plan(plan)


def _lock_order_for_production(
    order: Any,
    *,
    preserve_status: bool = False,
    plan_source: str = "System",
) -> dict[str, Any]:
    """Compatibility delegate for historical Python callers."""

    return _snapshot.lock_order_for_production(
        order,
        preserve_status=preserve_status,
        plan_source=plan_source,
    )


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
