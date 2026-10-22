"""Wire a verified inbound event into the existing accept/outbox path.

This module does not send WhatsApp replies. Live delivery stays gated by
``LIVE_REPLY_DELIVERY_ENABLED``. Durable reply intents are inserted inside the
same accept transaction used by the session store.
"""

from __future__ import annotations

from almdina_erp.almdina_erp.application.customer_bot.accept_inbound_message import (
    InboundAcceptance,
    accept_inbound_customer_message,
)
from almdina_erp.almdina_erp.domain.customer_bot.inbound_message import InboundCustomerMessage
from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_order_reader import (
    FrappeCustomerOrderReader,
)
from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_services import (
    build_customer_bot_services,
)
from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_session_repository import (
    FrappeCustomerBotSessionRepository,
)
from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_settings_repository import (
    FrappeCustomerBotSettingsRepository,
)
from almdina_erp.almdina_erp.infrastructure.frappe.customer_phone_directory import (
    FrappeCustomerPhoneDirectory,
)


def accept_verified_customer_bot_inbound(message: InboundCustomerMessage) -> InboundAcceptance:
    """Persist one trusted inbound event through the existing acceptance use case."""

    orders = FrappeCustomerOrderReader()
    return accept_inbound_customer_message(
        message,
        sessions=FrappeCustomerBotSessionRepository(),
        settings=FrappeCustomerBotSettingsRepository(),
        directory=FrappeCustomerPhoneDirectory(),
        headers=orders,
        stages=orders,
        routes=orders,
        services=build_customer_bot_services(),
        on_replies_committed=None,
    )


__all__ = ["accept_verified_customer_bot_inbound"]
