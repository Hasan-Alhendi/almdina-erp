"""Add the non-unique normalized mobile index and backfill it.

The patch is idempotent. A second run, including a later ``after_migrate``,
rewrites a row only when the stored index differs from the current
``Customer.mobile_no``. It does not enable the customer bot.
"""

from __future__ import annotations


def execute() -> None:
    from almdina_erp.almdina_erp.infrastructure.frappe.customer_phone_index import (
        sync_customer_normalized_mobile_index,
    )

    sync_customer_normalized_mobile_index()


__all__ = ["execute"]
