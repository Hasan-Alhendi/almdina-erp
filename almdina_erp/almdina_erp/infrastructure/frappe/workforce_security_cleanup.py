from __future__ import annotations

import frappe


ALMDINA_APP = "almdina_erp"
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
                "default_app": ALMDINA_APP,
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
            "default_app": ALMDINA_APP,
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

    The cleanup is deliberately scoped by ``User.default_app`` so it cannot strip
    System Manager from unrelated ERPNext administrators.
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
