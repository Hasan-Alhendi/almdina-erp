from __future__ import annotations

from typing import Any

import frappe
from frappe import _

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
    """Serialize dispatch against revision activation and route-specific gates."""

    _lock_and_validate(order_name)
    # The application command locks/reloads the order again before its decision.
    # That second boundary deliberately owns route, plan-approval, worker and
    # stage-creation checks so every dispatch path shares one authoritative rule.
    return shop_floor_commands.dispatch_order(order_name, path, assignee)


@frappe.whitelist()
def validate_order_for_dispatch(order_name: str) -> dict[str, Any]:
    """Validate only the route-independent prerequisites for opening dispatch UX.

    A selected route may add stricter requirements (for example an approved plan
    before a physical-first route). ``get_dispatch_options`` and ``dispatch_order``
    remain the authoritative route-aware boundaries.
    """

    order = _lock_and_validate(order_name)
    require_document_capability(
        order,
        Capability.DISPATCH_ORDER,
        message=_("لا تملك صلاحية إرسال هذا الطلب إلى الإنتاج."),
    )
    shop_floor_commands.assert_order_ready_for_dispatch(order)
    return {
        "name": order.name,
        "status": order.status,
        "revision_state": getattr(order, "revision_state", None) or "Current",
        "ready_for_route_selection": True,
        # Kept for old callers: true means the route-independent checks passed,
        # not that every production route is currently dispatchable.
        "ready_for_dispatch": True,
    }
