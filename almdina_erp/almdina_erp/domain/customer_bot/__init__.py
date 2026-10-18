"""Provider-neutral customer-bot rules.

This package does not send messages, open sessions, or identify a sender.
A gateway adapter, added later in infrastructure, maps a provider payload
onto these values after its own verification.
"""

from .gateway_capabilities import BotGatewayCapabilities
from .inbound_message import InboundCustomerMessage, InboundMessageKind, build_inbound_customer_message
from .text_reply import (
    SendDisposition,
    TextReplyRequest,
    TextSendResult,
    is_confirmed_rejection,
    is_unknown_send_outcome,
    provider_acceptance_confirms_customer_delivery,
)

__all__ = [
    "BotGatewayCapabilities",
    "InboundCustomerMessage",
    "InboundMessageKind",
    "SendDisposition",
    "TextReplyRequest",
    "TextSendResult",
    "build_inbound_customer_message",
    "is_confirmed_rejection",
    "is_unknown_send_outcome",
    "provider_acceptance_confirms_customer_delivery",
]
