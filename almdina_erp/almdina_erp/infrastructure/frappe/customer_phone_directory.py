"""Read current customer phones without loading orders or full customer documents.

Every non-empty ``Customer.mobile_no`` is normalized in memory. The query has
no row limit and does not keep the first match. Customer has no generated
phone index; this scan is the conflict-preserving lookup for the bot.
"""

from __future__ import annotations

import frappe

from almdina_erp.almdina_erp.domain.customer_bot.phone_number import (
    CustomerPhoneError,
    normalize_customer_phone,
)


class FrappeCustomerPhoneDirectory:
    def find_by_normalized_phone(self, normalized_phone: str) -> tuple[str, ...]:
        rows = frappe.get_all(
            "Customer",
            filters={"mobile_no": ["is", "set"]},
            fields=["name", "mobile_no"],
            limit_page_length=0,
        )
        matches: list[str] = []
        for row in rows:
            raw_phone = row.get("mobile_no") if isinstance(row, dict) else row.mobile_no
            customer_id = row.get("name") if isinstance(row, dict) else row.name
            try:
                normalized = normalize_customer_phone(str(raw_phone or ""))
            except CustomerPhoneError:
                continue
            if normalized == normalized_phone and customer_id not in matches:
                matches.append(str(customer_id))
        return tuple(matches)

    def customer_exists(self, customer_id: str) -> bool:
        if not str(customer_id or "").strip():
            return False
        return bool(frappe.db.exists("Customer", customer_id))


__all__ = ["FrappeCustomerPhoneDirectory"]
