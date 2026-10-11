from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any


_EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_LANGUAGE_CODE = re.compile(r"^[a-z]{2,3}(?:-[a-z0-9]{2,8})*$")
DEFAULT_USER_LANGUAGE = "ar"
MAX_USER_ROLES = 100


class WorkforceLanguageError(Exception):
    """Stable language-validation failure. Presentation translates ``code``."""

    def __init__(self, code: str, params: dict[str, str] | None = None) -> None:
        self.code = code
        self.params = dict(params or {})
        super().__init__(code)


def normalize_language_code(
    language: str,
    *,
    allowed_languages: Iterable[str] | None = None,
) -> str:
    """Validate a language code shape, and membership when a catalog is supplied.

    ``allowed_languages`` is an abstract set from the caller. This module does
    not read Frappe or decide which languages a site has enabled.
    """
    normalized = str(language or DEFAULT_USER_LANGUAGE).strip().lower().replace("_", "-")
    if not _LANGUAGE_CODE.fullmatch(normalized):
        raise WorkforceLanguageError("invalid_language_code", {"language": normalized})
    if allowed_languages is not None:
        allowed = {
            str(item or "").strip().lower().replace("_", "-")
            for item in allowed_languages
            if str(item or "").strip()
        }
        if normalized not in allowed:
            raise WorkforceLanguageError("unsupported_language", {"language": normalized})
    return normalized


@dataclass(frozen=True, slots=True)
class WorkforceIdentity:
    email: str
    first_name: str
    last_name: str
    language: str


def normalize_identity(
    *,
    email: str,
    first_name: str,
    last_name: str = "",
    language: str = DEFAULT_USER_LANGUAGE,
    allowed_languages: Iterable[str] | None = None,
) -> WorkforceIdentity:
    normalized_email = str(email or "").strip().lower()
    normalized_first = " ".join(str(first_name or "").split())
    normalized_last = " ".join(str(last_name or "").split())
    normalized_language = normalize_language_code(
        language,
        allowed_languages=allowed_languages,
    )

    if not _EMAIL_PATTERN.match(normalized_email):
        raise ValueError("يجب إدخال بريد إلكتروني صالح للمستخدم.")
    if not normalized_first:
        raise ValueError("الاسم الأول للمستخدم مطلوب.")
    if len(normalized_first) > 140 or len(normalized_last) > 140:
        raise ValueError("اسم المستخدم أطول من الحد المسموح.")

    return WorkforceIdentity(
        email=normalized_email,
        first_name=normalized_first,
        last_name=normalized_last,
        language=normalized_language,
    )


def normalize_role_selection(roles: Iterable[str] | None) -> tuple[str, ...]:
    if roles is None:
        return ()
    if isinstance(roles, (str, bytes)):
        raise ValueError("يجب إرسال أدوار المستخدم على شكل قائمة.")
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_role in roles:
        role = str(raw_role or "").strip()
        if not role:
            raise ValueError("لا يجوز أن تحتوي قائمة أدوار المستخدم على قيمة فارغة.")
        if role in seen:
            continue
        seen.add(role)
        normalized.append(role)
    if len(normalized) > MAX_USER_ROLES:
        raise ValueError(f"لا يمكن إسناد أكثر من {MAX_USER_ROLES} دور للمستخدم.")
    return tuple(normalized)


def validate_temporary_password(password: str, *, email: str = "") -> str:
    value = str(password or "")
    if len(value) < 10:
        raise ValueError("يجب أن تتكون كلمة المرور المؤقتة من 10 محارف على الأقل.")
    if not any(character.isalpha() for character in value):
        raise ValueError("يجب أن تحتوي كلمة المرور المؤقتة على حرف واحد على الأقل.")
    if not any(character.isdigit() for character in value):
        raise ValueError("يجب أن تحتوي كلمة المرور المؤقتة على رقم واحد على الأقل.")
    local_part = str(email or "").split("@", 1)[0].strip().lower()
    if local_part and len(local_part) >= 4 and local_part in value.lower():
        raise ValueError("يجب ألا تحتوي كلمة المرور المؤقتة على اسم البريد الإلكتروني قبل علامة @.")
    return value


def audit_snapshot(user: dict[str, Any] | None) -> dict[str, Any]:
    source = dict(user or {})
    roles = normalize_role_selection(source.get("roles") or ())
    return {
        "email": str(source.get("email") or source.get("name") or ""),
        "first_name": str(source.get("first_name") or ""),
        "last_name": str(source.get("last_name") or ""),
        "full_name": str(source.get("full_name") or ""),
        "enabled": bool(source.get("enabled")),
        "language": str(source.get("language") or ""),
        "roles": list(roles),
        "default_workspace": str(source.get("default_workspace") or ""),
        "default_app": str(source.get("default_app") or ""),
    }


__all__ = [
    "DEFAULT_USER_LANGUAGE",
    "MAX_USER_ROLES",
    "WorkforceIdentity",
    "WorkforceLanguageError",
    "audit_snapshot",
    "normalize_identity",
    "normalize_language_code",
    "normalize_role_selection",
    "validate_temporary_password",
]
