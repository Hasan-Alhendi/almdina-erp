"""Callback path for the customer-bot inbound method.

Domain joins this path to the site's public base. The method name stays here
because renaming it would change an already registered webhook URL.
"""

from __future__ import annotations

CUSTOMER_BOT_CALLBACK_PATH = (
    "/api/method/almdina_erp.almdina_erp.services.customer_bot_inbound_service"
    ".receive_openwa_customer_bot_event"
)

__all__ = ["CUSTOMER_BOT_CALLBACK_PATH"]
