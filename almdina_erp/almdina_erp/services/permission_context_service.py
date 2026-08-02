from __future__ import annotations

from typing import Any

import frappe

from almdina_erp.almdina_erp.application.security.permission_context import (
    build_permission_context,
)
from almdina_erp.almdina_erp.infrastructure.frappe.authorization_gateway import (
    granted_capabilities,
)


@frappe.whitelist()
def get_permission_context() -> dict[str, Any]:
    """Return the current user's capability context without mutating session data."""

    return build_permission_context(
        (),
        granted_capabilities(user=frappe.session.user),
    )


__all__ = ["get_permission_context"]
