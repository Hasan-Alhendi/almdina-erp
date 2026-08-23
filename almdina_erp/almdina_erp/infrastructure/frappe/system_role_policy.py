from __future__ import annotations


# Frappe attaches some system roles automatically or treats them as platform-wide
# administration roles. They are never editable sources of Almdina business
# authority. Administrator remains the explicit superuser exception.
PROTECTED_SYSTEM_ROLES = frozenset(
    {"All", "Guest", "Desk User", "System Manager"}
)


def is_protected_system_role(role: str | None) -> bool:
    return str(role or "").strip() in PROTECTED_SYSTEM_ROLES


__all__ = ["PROTECTED_SYSTEM_ROLES", "is_protected_system_role"]
