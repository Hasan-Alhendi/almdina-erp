"""Customer-bot use cases.

The reply port is injected here. Connection secrets, provider payloads, and
session setup stay outside this package.
"""

from .dispatch_text_reply import dispatch_text_reply
from .errors import BotReplyPortError
from .ports import BotTextReplyPort

__all__ = [
    "BotReplyPortError",
    "BotTextReplyPort",
    "dispatch_text_reply",
]
