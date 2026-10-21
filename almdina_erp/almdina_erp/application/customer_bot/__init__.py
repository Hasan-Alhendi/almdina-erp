"""Customer-bot use cases.

The reply port is injected here. Connection secrets, provider payloads, and
session setup stay outside this package.
"""

from .conversation_ports import CustomerBotServiceRouter, UnavailableCustomerBotServices
from .dispatch_text_reply import dispatch_text_reply
from .errors import BotReplyPortError
from .handle_conversation import handle_customer_conversation
from .final_price_service import (
    CustomerBotFinalPriceService,
    CustomerBotFinalPriceSnapshot,
)
from .approved_plan_service import (
    CustomerBotApprovedPlanService,
    CustomerBotApprovedPlanSnapshot,
)
from .phone_access_commands import (
    PhoneAccessRetired,
    approve_phone_access_request,
    reject_phone_access_request,
    request_additional_phone_access,
    revoke_phone_access,
)
from .ports import BotTextReplyPort
from .read_customer_orders import (
    list_current_customer_orders,
    select_customer_order_by_name,
)
from .resolve_customer_identity import resolve_customer_identity

__all__ = [
    "BotReplyPortError",
    "BotTextReplyPort",
    "PhoneAccessRetired",
    "approve_phone_access_request",
    "UnavailableCustomerBotServices",
    "CustomerBotServiceRouter",
    "dispatch_text_reply",
    "handle_customer_conversation",
    "CustomerBotFinalPriceService",
    "CustomerBotFinalPriceSnapshot",
    "CustomerBotApprovedPlanService",
    "CustomerBotApprovedPlanSnapshot",
    "list_current_customer_orders",
    "reject_phone_access_request",
    "request_additional_phone_access",
    "resolve_customer_identity",
    "select_customer_order_by_name",
    "revoke_phone_access",
]
