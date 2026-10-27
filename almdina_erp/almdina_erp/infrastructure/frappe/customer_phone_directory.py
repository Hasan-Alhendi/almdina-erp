"""Resolve a normalized phone through the server-owned customer index.

``Customer.mobile_no`` remains the source of truth. The lookup reads the
normalized column for that exact value and returns every match so a shared
number stays a conflict. It does not load every customer and it does not cache
ownership.
"""

from __future__ import annotations

import frappe

from .customer_phone_index import customer_ids_for_indexed_phone


class FrappeCustomerPhoneDirectory:
    def find_by_normalized_phone(self, normalized_phone: str) -> tuple[str, ...]:
        return customer_ids_for_indexed_phone(normalized_phone)

    def customer_exists(self, customer_id: str) -> bool:
        if not str(customer_id or "").strip():
            return False
        return bool(frappe.db.exists("Customer", customer_id))


__all__ = ["FrappeCustomerPhoneDirectory"]
