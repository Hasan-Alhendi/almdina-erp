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
    MAX_SESSION_NAME_ATTEMPTS,
    QR_STATUSES,
    SESSION_NAME_PREFIX,
    WORKING_STATUS,
    CreateSessionDecision,
    SessionNameError,
    is_working,
    needs_qr,
    sessions_named,
    should_create_session,
    unique_session_name,
)

__all__ = [
    "MAX_SESSION_NAME_ATTEMPTS",
    "QR_STATUSES",
    "SESSION_NAME_PREFIX",
    "WORKING_STATUS",
    "CreateSessionDecision",
    "SessionNameError",
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
    "sessions_named",
    "should_create_session",
    "unique_session_name",
]
