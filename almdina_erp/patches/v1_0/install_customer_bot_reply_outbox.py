"""Add the reply-intent unique keys. Existing bot settings and sessions stay put.

A successful Patch Log row is not the schema. ``after_install`` and
``after_migrate`` call the same function, so a site that logged this patch
before the indexes existed is repaired by the next ordinary migrate.
"""

from __future__ import annotations


def execute() -> None:
    from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_schema import (
        ensure_customer_bot_reply_unique_indexes,
    )

    ensure_customer_bot_reply_unique_indexes()
