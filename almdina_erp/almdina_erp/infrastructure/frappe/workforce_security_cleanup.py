from __future__ import annotations

import frappe

from almdina_erp.almdina_erp.infrastructure.frappe.workforce_membership import (
    MEMBERSHIP_FIELD,
)


HIDDEN_PRIVILEGED_ROLE = "System Manager"


def _almdina_workforce_users() -> tuple[str, ...]:
    """Return only application-scoped System Users managed by Almdina."""

    if not frappe.db.exists("DocType", "User"):
        return ()
    return tuple(
        str(user)
        for user in frappe.get_all(
            "User",
            filters={
                "user_type": "System User",
                MEMBERSHIP_FIELD: 1,
                "name": ["not in", ["Administrator", "Guest"]],
            },
            pluck="name",
            limit=0,
        )
        if user
    )


def revoke_hidden_system_manager_from_user(user: str) -> bool:
    """Remove a hidden platform-admin role from one Almdina workforce account."""

    resolved = str(user or "").strip().lower()
    if not resolved:
        return False
    if not frappe.db.exists(
        "User",
        {
            "name": resolved,
            "user_type": "System User",
            MEMBERSHIP_FIELD: 1,
        },
    ):
        return False

    filters = {
        "parent": resolved,
        "parenttype": "User",
        "role": HIDDEN_PRIVILEGED_ROLE,
    }
    if not frappe.db.exists("Has Role", filters):
        return False

    frappe.db.delete("Has Role", filters)
    request_cache = getattr(frappe.local, "almdina_matrix_capabilities", None)
    if request_cache is not None:
        request_cache.pop(resolved, None)
    frappe.clear_cache(user=resolved)
    return True


def revoke_hidden_system_manager_from_almdina_workforce() -> int:
    """Repair legacy Almdina users that silently retained System Manager.

    Membership is application-owned and deliberately independent from Frappe's
    default_app/default_workspace navigation preferences.
    """

    removed = 0
    for user in _almdina_workforce_users():
        if revoke_hidden_system_manager_from_user(user):
            removed += 1
    return removed


__all__ = [
    "revoke_hidden_system_manager_from_almdina_workforce",
    "revoke_hidden_system_manager_from_user",
]
