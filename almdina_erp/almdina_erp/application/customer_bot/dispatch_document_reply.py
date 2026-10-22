"""Send one document reply through an injected port.

The port must return the same reply id, connection, and destination. An
exception raised here is not rewritten into an unknown send result.
"""

from __future__ import annotations

from almdina_erp.almdina_erp.domain.customer_bot.document_reply import DocumentReplyRequest
from almdina_erp.almdina_erp.domain.customer_bot.text_reply import TextSendResult

from .errors import BotReplyPortError
from .ports import BotDocumentReplyPort


def dispatch_document_reply(port: BotDocumentReplyPort, request: DocumentReplyRequest) -> TextSendResult:
    if not isinstance(request, DocumentReplyRequest):
        raise TypeError("request must be a DocumentReplyRequest")
    result = port.send_document_reply(request)
    if not isinstance(result, TextSendResult):
        raise BotReplyPortError("document reply port returned a result in an unknown shape")
    if (
        result.reply_id != request.reply_id
        or result.connection_ref != request.connection_ref
        or result.destination_id != request.destination_id
    ):
        raise BotReplyPortError("document reply port changed the reply id, connection, or destination")
    return result


__all__ = ["dispatch_document_reply"]
