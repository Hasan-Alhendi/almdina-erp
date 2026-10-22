"""Ensure the inbound OpenWA capability column exists.

Connection fields live on Customer Bot Settings via DocType sync. This patch
does not invent a secret, session id, connection ref, or integration user.
"""

from __future__ import annotations


def execute() -> None:
    from almdina_erp.almdina_erp.infrastructure.frappe.permission_type_sync import (
        sync_permission_types,
    )

    sync_permission_types()


__all__ = ["execute"]
