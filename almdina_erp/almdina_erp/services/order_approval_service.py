from __future__ import annotations

from typing import Any

import frappe

from almdina_erp.almdina_erp.application.orders.lifecycle_permissions import (
    OrderLifecycleAction,
)
from almdina_erp.almdina_erp.services.cutting_plan_service import (
    _lock_order_for_production,
)
from almdina_erp.almdina_erp.services.order_lifecycle_permission_service import (
    require_lifecycle_action,
)
from almdina_erp.almdina_erp.services.order_revision_activation import (
    finalize_revision_activation,
    load_locked_revision_order,
    prepare_revision_activation,
)


@frappe.whitelist()
def approve_order(order_name: str) -> dict[str, Any]:
    """Approve an order and atomically activate a pending revision when needed."""

    order = load_locked_revision_order(order_name)
    order.check_permission("read")
    require_lifecycle_action(order, OrderLifecycleAction.APPROVE)

    activation_context = prepare_revision_activation(order)
    result = _lock_order_for_production(order)
    activation = finalize_revision_activation(
        order,
        activation_context,
        new_plan_name=result.get("cutting_plan"),
    )
    result["revision_activation"] = activation
    return result
