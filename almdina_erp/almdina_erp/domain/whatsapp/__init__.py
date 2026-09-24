"""WhatsApp delivery rules that stay independent of Frappe and OpenWA."""

from .message_templates import (
    DOCUMENT_CAPTION_MAX_LENGTH,
    INVOICE_TEXT_TEMPLATE,
    MEASUREMENT_AMENDMENTS_TEXT_TEMPLATE,
    MEASUREMENTS_TEXT_TEMPLATE,
    STAGE_COMPLETION_TEXT_TEMPLATE,
    DocumentCaptionError,
    document_caption,
    format_whatsapp_preamble,
)
from .phone import PhoneNormalizationError, normalize_syrian_whatsapp_chat_id
from .session_policy import (
    FACTORY_SESSION_NAME,
    QR_STATUSES,
    WORKING_STATUS,
    CreateSessionDecision,
    is_working,
    needs_qr,
    select_factory_session,
    should_create_session,
)

__all__ = [
    "FACTORY_SESSION_NAME",
    "QR_STATUSES",
    "WORKING_STATUS",
    "CreateSessionDecision",
    "DOCUMENT_CAPTION_MAX_LENGTH",
    "DocumentCaptionError",
    "INVOICE_TEXT_TEMPLATE",
    "MEASUREMENT_AMENDMENTS_TEXT_TEMPLATE",
    "MEASUREMENTS_TEXT_TEMPLATE",
    "STAGE_COMPLETION_TEXT_TEMPLATE",
    "PhoneNormalizationError",
    "document_caption",
    "format_whatsapp_preamble",
    "is_working",
    "needs_qr",
    "normalize_syrian_whatsapp_chat_id",
    "select_factory_session",
    "should_create_session",
]
