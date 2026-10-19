"""Customer-bot use cases.

The reply port is injected here. Connection secrets, provider payloads, and
session setup stay outside this package.
"""

from .dispatch_text_reply import dispatch_text_reply
from .errors import BotReplyPortError
from .phone_access_commands import (
    PhoneAccessRetired,
    approve_phone_access_request,
    reject_phone_access_request,
    request_additional_phone_access,
    revoke_phone_access,
)
from .ports import BotTextReplyPort
from .resolve_customer_identity import resolve_customer_identity

__all__ = [
    "BotReplyPortError",
    "BotTextReplyPort",
    "PhoneAccessRetired",
    "approve_phone_access_request",
    "dispatch_text_reply",
    "reject_phone_access_request",
    "request_additional_phone_access",
    "resolve_customer_identity",
    "revoke_phone_access",
]
