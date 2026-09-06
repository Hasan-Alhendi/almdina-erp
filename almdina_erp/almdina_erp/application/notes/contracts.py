from __future__ import annotations

import re


ORDER_DOCTYPE = "Door Cutting Order"
CUSTOMER_DOCTYPE = "Customer"
ALLOWED_REFERENCE_DOCTYPES = frozenset({ORDER_DOCTYPE, CUSTOMER_DOCTYPE})
NOTE_MAX_LENGTH = 500
IMPORTANT_PREVIEW_LENGTH = 140
NOTE_SUBJECT_PREFIX = "almdina-note:"
_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$")
_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_FALSE_VALUES = frozenset({"0", "false", "no", "off", ""})


class NotesValidationError(ValueError):
    """Raised when a collaborative-note command violates its public contract."""


def normalize_reference(reference_doctype: object, reference_name: object) -> tuple[str, str]:
    doctype = str(reference_doctype or "").strip()
    name = str(reference_name or "").strip()
    if doctype not in ALLOWED_REFERENCE_DOCTYPES:
        raise NotesValidationError("نوع مرجع الملاحظة غير مدعوم.")
    if not name:
        raise NotesValidationError("يجب تحديد السجل المرتبط بالملاحظة.")
    return doctype, name


def normalize_note_content(content: object) -> str:
    resolved = str(content or "").strip()
    if not resolved:
        raise NotesValidationError("لا يمكن إضافة ملاحظة فارغة.")
    if len(resolved) > NOTE_MAX_LENGTH:
        raise NotesValidationError(
            f"يجب ألا تتجاوز الملاحظة {NOTE_MAX_LENGTH} محرفًا."
        )
    return resolved


def normalize_request_id(request_id: object) -> str:
    resolved = str(request_id or "").strip()
    if not _REQUEST_ID_PATTERN.fullmatch(resolved):
        raise NotesValidationError("معرّف طلب الملاحظة غير صالح.")
    return resolved


def normalize_boolean_flag(value: object, *, label: str = "القيمة") -> bool:
    """Normalize Frappe form/RPC boolean encodings without truthy-string bugs."""

    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    normalized = str(value or "").strip().lower()
    if normalized in _TRUE_VALUES:
        return True
    if normalized in _FALSE_VALUES:
        return False
    raise NotesValidationError(f"{label} غير صالحة.")


def request_subject(request_id: object) -> str:
    return f"{NOTE_SUBJECT_PREFIX}{normalize_request_id(request_id)}"


def is_collaborative_note_subject(subject: object) -> bool:
    """Identify Comments owned by the Almadina collaborative-notes boundary."""

    return str(subject or "").strip().startswith(NOTE_SUBJECT_PREFIX)


def plain_text_preview(content: object, limit: int = IMPORTANT_PREVIEW_LENGTH) -> str:
    resolved = " ".join(str(content or "").split())
    bounded_limit = max(1, int(limit or IMPORTANT_PREVIEW_LENGTH))
    if len(resolved) <= bounded_limit:
        return resolved
    return f"{resolved[: max(1, bounded_limit - 1)].rstrip()}…"


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
