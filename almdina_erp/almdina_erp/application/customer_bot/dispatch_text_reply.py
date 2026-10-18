"""Send one text reply through an injected port.

This is the step-1 use case only. It does not choose menus, read orders, or
retry. An adapter that loses the outcome must return UNKNOWN itself; an
exception raised here is not rewritten into an unknown send result.
"""

from __future__ import annotations

from almdina_erp.almdina_erp.domain.customer_bot.gateway_capabilities import (
    BotGatewayCapabilities,
)
from almdina_erp.almdina_erp.domain.customer_bot.text_reply import (
    SendDisposition,
    TextReplyRequest,
    TextSendResult,
)

from .errors import BotReplyPortError
from .ports import BotTextReplyPort


def dispatch_text_reply(port: BotTextReplyPort, request: TextReplyRequest) -> TextSendResult:
    if not isinstance(request, TextReplyRequest):
        raise TypeError("request must be a TextReplyRequest")
    capabilities = port.capabilities()
    if not isinstance(capabilities, BotGatewayCapabilities):
        raise BotReplyPortError("reply port returned capabilities in an unknown shape")
    if not capabilities.sends_text:
        return TextSendResult(
            reply_id=request.reply_id,
            connection_ref=request.connection_ref,
            destination_id=request.destination_id,
            disposition=SendDisposition.REJECTED,
            provider_message_id=None,
            reason_code="text_send_unsupported",
        )
    result = port.send_text_reply(request)
    if not isinstance(result, TextSendResult):
        raise BotReplyPortError("reply port returned a result in an unknown shape")
    if (
        result.reply_id != request.reply_id
        or result.connection_ref != request.connection_ref
        or result.destination_id != request.destination_id
    ):
        raise BotReplyPortError("reply port changed the reply id, connection, or destination")
    return result
