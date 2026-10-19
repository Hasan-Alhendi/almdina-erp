"""Internal wiring for customer-bot order reads.

These functions have no guest endpoint. The phone is the value a future
inbound adapter has already verified. They are not an endpoint that accepts
a phone chosen by a desk user.
"""

from __future__ import annotations

from almdina_erp.almdina_erp.application.customer_bot.read_customer_orders import (
    list_current_customer_orders,
    select_customer_order_by_name,
)
from almdina_erp.almdina_erp.domain.customer_bot.order_followup import (
    CurrentOrderList,
    OrderSelection,
)
from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_order_reader import (
    FrappeCustomerOrderReader,
)
from almdina_erp.almdina_erp.infrastructure.frappe.customer_phone_directory import (
    FrappeCustomerPhoneDirectory,
)


def list_current_orders_for_phone(phone: str) -> CurrentOrderList:
    reader = FrappeCustomerOrderReader()
    return list_current_customer_orders(
        FrappeCustomerPhoneDirectory(),
        reader,
        reader,
        reader,
        phone,
    )


def select_order_for_phone(phone: str, order_name: str) -> OrderSelection:
    reader = FrappeCustomerOrderReader()
    return select_customer_order_by_name(
        FrappeCustomerPhoneDirectory(),
        reader,
        reader,
        reader,
        phone,
        order_name,
    )


__all__ = [
    "list_current_orders_for_phone",
    "select_order_for_phone",
]
