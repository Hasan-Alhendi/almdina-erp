"""Frappe bindings for the provider-neutral customer-bot service port."""

from __future__ import annotations

from almdina_erp.almdina_erp.application.customer_bot.final_price_service import (
    CustomerBotFinalPriceService,
)
from almdina_erp.almdina_erp.application.customer_bot.approved_plan_service import (
    CustomerBotApprovedPlanService,
)
from almdina_erp.almdina_erp.application.customer_bot.conversation_ports import (
    CustomerBotServiceRouter,
)

from .customer_bot_approved_plan_reader import FrappeCustomerBotApprovedPlanReader
from .customer_bot_cutting_plan_pdf import FrappeCustomerBotCuttingPlanPdfAdapter
from .customer_bot_final_price_reader import FrappeCustomerBotFinalPriceReader
from .customer_bot_invoice_pdf import FrappeCustomerBotInvoicePdfAdapter


def build_customer_bot_services() -> CustomerBotServiceRouter:
    """Bind options 2 and 3 to read-only Frappe adapters."""

    return CustomerBotServiceRouter(
        CustomerBotFinalPriceService(
            FrappeCustomerBotFinalPriceReader(),
            FrappeCustomerBotInvoicePdfAdapter(),
        ),
        CustomerBotApprovedPlanService(
            FrappeCustomerBotApprovedPlanReader(),
            FrappeCustomerBotCuttingPlanPdfAdapter(),
        ),
    )


__all__ = ["build_customer_bot_services"]
