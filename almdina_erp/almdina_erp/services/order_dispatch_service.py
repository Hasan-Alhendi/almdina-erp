from __future__ import annotations

from typing import Any

import frappe

from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe.authorization_gateway import (
    require_document_capability,
)
from almdina_erp.almdina_erp.services import shop_floor_commands
from almdina_erp.almdina_erp.services.order_revision_activation import (
    assert_order_revision_dispatchable,
    load_locked_revision_order,
)


def _lock_and_validate(order_name: str) -> Any:
    order = load_locked_revision_order(order_name)
    assert_order_revision_dispatchable(order)
    return order


@frappe.whitelist()
def dispatch_order(order_name: str, path: str, assignee: str) -> dict[str, Any]:
    """Serialize dispatch against revision activation and reject stale revisions."""

    _lock_and_validate(order_name)
    return shop_floor_commands.dispatch_order(order_name, path, assignee)


@frappe.whitelist()
def validate_order_for_dispatch(order_name: str) -> dict[str, Any]:
    """Backward-compatible pre-dispatch validation using the same capability."""

    order = _lock_and_validate(order_name)
    require_document_capability(
        order,
        Capability.DISPATCH_ORDER,
        message="You do not have permission to send this order to production.",
    )
    shop_floor_commands.assert_order_ready_for_dispatch(order)
    return {
        "name": order.name,
        "status": order.status,
        "revision_state": getattr(order, "revision_state", None) or "Current",
        "ready_for_dispatch": True,
    }
