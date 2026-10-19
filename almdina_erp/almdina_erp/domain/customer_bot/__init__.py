"""Provider-neutral customer-bot rules.

Inbound messages still do not prove who sent them. Phone matching uses a
number the gateway adapter has already verified, and that match is not tied
to a provider name or session id.
"""

from .gateway_capabilities import BotGatewayCapabilities
from .inbound_message import InboundCustomerMessage, InboundMessageKind, build_inbound_customer_message
from .order_followup import (
    PublicOrderStatus,
    classify_public_order_status,
)
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
    "PublicOrderStatus",
    "classify_public_order_status",
    "SendDisposition",
    "TextReplyRequest",
    "TextSendResult",
    "build_inbound_customer_message",
    "is_confirmed_rejection",
    "is_unknown_send_outcome",
    "provider_acceptance_confirms_customer_delivery",
]
