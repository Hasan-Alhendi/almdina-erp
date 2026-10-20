"""Frappe bindings for the provider-neutral customer-bot service port."""

from __future__ import annotations

from almdina_erp.almdina_erp.application.customer_bot.final_price_service import (
    CustomerBotFinalPriceService,
)

from .customer_bot_final_price_reader import FrappeCustomerBotFinalPriceReader
from .customer_bot_invoice_pdf import FrappeCustomerBotInvoicePdfAdapter


def build_customer_bot_services() -> CustomerBotFinalPriceService:
    """Bind option 2 to read-only Frappe adapters for the future inbound layer."""

    return CustomerBotFinalPriceService(
        FrappeCustomerBotFinalPriceReader(),
        FrappeCustomerBotInvoicePdfAdapter(),
    )


__all__ = ["build_customer_bot_services"]
