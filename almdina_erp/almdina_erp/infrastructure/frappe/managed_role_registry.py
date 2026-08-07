from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import cint


ROLE_METADATA_DOCTYPE = "Almdina Role Metadata"


def metadata_available() -> bool:
    return bool(frappe.db.exists("DocType", ROLE_METADATA_DOCTYPE))


def managed_role_metadata() -> dict[str, dict[str, Any]]:
    """Return the canonical Almdina-owned role registry keyed by Role name."""

    if not metadata_available():
        return {}
    rows = frappe.get_all(
        ROLE_METADATA_DOCTYPE,
        filters={"managed_by_almdina": 1},
        fields=["name", "role", "role_uid", "description", "managed_by_almdina"],
        limit_page_length=0,
    )
    return {
        str(row.role): {
            "name": str(row.name),
            "role": str(row.role),
            "role_uid": str(row.role_uid or ""),
            "description": str(row.description or ""),
            "managed_by_almdina": bool(cint(row.managed_by_almdina)),
        }
        for row in rows
        if str(row.role or "").strip()
    }


def managed_role_names() -> frozenset[str]:
    return frozenset(managed_role_metadata())


def is_managed_role(role: str) -> bool:
    return str(role or "").strip() in managed_role_names()


__all__ = [
    "ROLE_METADATA_DOCTYPE",
    "is_managed_role",
    "managed_role_metadata",
    "managed_role_names",
    "metadata_available",
]
