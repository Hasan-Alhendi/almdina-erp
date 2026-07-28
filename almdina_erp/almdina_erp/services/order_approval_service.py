from __future__ import annotations

from typing import Any

import frappe
from frappe import _

from almdina_erp.almdina_erp.services.cutting_plan_service import (
    _lock_order_for_production,
    require_any_role,
)
from almdina_erp.almdina_erp.services.order_revision_activation import (
    finalize_revision_activation,
    load_locked_revision_order,
    prepare_revision_activation,
)


@frappe.whitelist()
def approve_order(order_name: str) -> dict[str, Any]:
    """Approve an order and atomically activate a pending revision when needed."""

    require_any_role("Production Manager")
    order = load_locked_revision_order(order_name)
    if order.status not in {"Draft", "Rejected", "Pending Review"}:
        frappe.throw(_("Only Draft, Rejected or Pending Review orders can be approved."))

    activation_context = prepare_revision_activation(order)
    result = _lock_order_for_production(order)
    activation = finalize_revision_activation(
        order,
        activation_context,
        new_plan_name=result.get("cutting_plan"),
    )
    result["revision_activation"] = activation
    return result
