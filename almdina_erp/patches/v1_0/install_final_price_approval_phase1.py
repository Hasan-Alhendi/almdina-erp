from __future__ import annotations

import frappe

from almdina_erp.almdina_erp.domain.orders.price_approval import (
    PRICE_APPROVAL_STATUS_UNAPPROVED,
)
from almdina_erp.almdina_erp.infrastructure.frappe.permission_type_sync import (
    sync_permission_types,
)


def execute() -> None:
    """Register the capability Permission Type and backfill Unapproved status.

    Idempotent:
    - sync_permission_types only inserts/repairs Permission Type rows
    - status backfill only fills blank/null values and never overwrites Approved
    - no role is granted approve_final_price
    - no Door Cutting Price Approval rows are created
    """

    sync_permission_types()

    if not frappe.db.has_column("Door Cutting Order", "price_approval_status"):
        return

    frappe.db.sql(
        """
        update `tabDoor Cutting Order`
        set price_approval_status = %(status)s
        where ifnull(price_approval_status, '') = ''
        """,
        {"status": PRICE_APPROVAL_STATUS_UNAPPROVED},
    )


__all__ = ["execute"]
