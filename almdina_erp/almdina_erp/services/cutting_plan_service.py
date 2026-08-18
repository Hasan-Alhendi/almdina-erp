"""Backward-compatible Cutting Plan lifecycle facade.

Historical whitelisted endpoint paths remain available here as thin delegates to
the focused canonical services. The pre-A6 Python snapshot persistence helpers
are retained only as fail-closed migration stubs; they must never recreate Plan
state from ``Door Cutting Order``.
"""

from __future__ import annotations

from typing import Any, NoReturn

import frappe
from frappe import _


_RETIRED_SNAPSHOT_MESSAGE = _(
    "The legacy Door Cutting Order snapshot API has been retired. "
    "Use the canonical Cutting Plan command services."
)


def _retired_snapshot_api() -> NoReturn:
    frappe.throw(_RETIRED_SNAPSHOT_MESSAGE, frappe.ValidationError)
    raise AssertionError("frappe.throw must interrupt execution")


def create_plan_from_order(
    order: Any,
    snapshot_override: dict[str, Any] | None = None,
    *,
    plan_kind: str = "Order",
) -> NoReturn:
    """Reject the former DCO-to-Cutting-Plan snapshot constructor."""

    del order, snapshot_override, plan_kind
    _retired_snapshot_api()


def approve_plan(plan: Any) -> NoReturn:
    """Reject the former direct Plan approval bypass."""

    del plan
    _retired_snapshot_api()


def _lock_order_for_production(
    order: Any,
    *,
    preserve_status: bool = False,
    plan_source: str = "System",
) -> NoReturn:
    """Reject the retired Python production-plan lock path."""

    del order, preserve_status, plan_source
    _retired_snapshot_api()


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
