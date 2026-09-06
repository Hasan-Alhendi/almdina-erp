"""Framework-independent collaborative notes contracts."""

from .contracts import (
    ALLOWED_REFERENCE_DOCTYPES,
    CUSTOMER_DOCTYPE,
    IMPORTANT_PREVIEW_LENGTH,
    NOTE_MAX_LENGTH,
    NOTE_SUBJECT_PREFIX,
    ORDER_DOCTYPE,
    NotesValidationError,
    is_collaborative_note_subject,
    normalize_boolean_flag,
    normalize_note_content,
    normalize_reference,
    normalize_request_id,
    plain_text_preview,
    request_subject,
)

__all__ = [
    "ALLOWED_REFERENCE_DOCTYPES",
    "CUSTOMER_DOCTYPE",
    "IMPORTANT_PREVIEW_LENGTH",
    "NOTE_MAX_LENGTH",
    "NOTE_SUBJECT_PREFIX",
    "ORDER_DOCTYPE",
    "NotesValidationError",
    "is_collaborative_note_subject",
    "normalize_boolean_flag",
    "normalize_note_content",
    "normalize_reference",
    "normalize_request_id",
    "plain_text_preview",
    "request_subject",
]
