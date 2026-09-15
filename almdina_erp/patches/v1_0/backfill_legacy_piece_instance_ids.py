from __future__ import annotations

from uuid import NAMESPACE_URL, uuid5

import frappe


DETAIL_DOCTYPE = "Door Cutting Order Detail"
BATCH_SIZE = 500


def execute() -> None:
    """Backfill stable identities for legacy order pieces without touching existing IDs."""
    if not frappe.db.table_exists(DETAIL_DOCTYPE):
        return

    while True:
        rows = frappe.db.sql(
            """
            select name
            from `tabDoor Cutting Order Detail`
            where parenttype = 'Door Cutting Order'
              and coalesce(trim(piece_instance_id), '') = ''
            order by name
            limit %s
            """,
            (BATCH_SIZE,),
            as_dict=True,
        )
        if not rows:
            return

        for row in rows:
            frappe.db.set_value(
                DETAIL_DOCTYPE,
                row.name,
                "piece_instance_id",
                legacy_piece_instance_id(row.name),
                update_modified=False,
            )


def legacy_piece_instance_id(row_name: str) -> str:
    """Return a deterministic identity so retries cannot assign a different physical ID."""
    identity = uuid5(
        NAMESPACE_URL,
        f"almdina-erp:door-cutting-order-detail:{row_name}",
    )
    return f"piece:{identity.hex}"
