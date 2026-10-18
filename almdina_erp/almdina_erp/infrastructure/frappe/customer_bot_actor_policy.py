"""Employee authority for additional-phone decisions.

``Administrator`` remains the explicit exception. ``System Manager`` and the
WhatsApp session or message capabilities do not grant this decision.
"""

from __future__ import annotations

from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe.authorization_gateway import (
    doctype_has_capability,
)
from almdina_erp.resource_permissions import customer_has_permission


class FrappeCustomerBotActorPolicy:
    def has_manage_access(self, actor_id: str) -> bool:
        if actor_id == "Guest" or not actor_id:
            return False
        return doctype_has_capability(
            Capability.MANAGE_CUSTOMER_BOT_ACCESS,
            user=actor_id,
        )

    def can_access_customer(self, actor_id: str, customer_id: str) -> bool:
        if not customer_id or actor_id == "Guest":
            return False
        return bool(customer_has_permission(customer_id, user=actor_id, ptype="read"))


__all__ = ["FrappeCustomerBotActorPolicy"]
