"""Security-related application use cases.

Framework-dependent provisioning is loaded lazily so pure authorization and
permission-context use cases remain importable in static tests without Frappe.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "PERMISSION_CONTEXT_VERSION",
    "PROFILES",
    "build_permission_context",
    "provision_user",
]


def __getattr__(name: str) -> Any:
    if name in {"PERMISSION_CONTEXT_VERSION", "build_permission_context"}:
        from .permission_context import (
            PERMISSION_CONTEXT_VERSION,
            build_permission_context,
        )

        value = {
            "PERMISSION_CONTEXT_VERSION": PERMISSION_CONTEXT_VERSION,
            "build_permission_context": build_permission_context,
        }[name]
    elif name in {"PROFILES", "provision_user"}:
        from .provision_user import PROFILES, provision_user

        value = {"PROFILES": PROFILES, "provision_user": provision_user}[name]
    else:
        raise AttributeError(name)

    globals()[name] = value
    return value
