from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any


_EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
SUPPORTED_LANGUAGES = frozenset({"ar", "en"})
MAX_USER_ROLES = 100


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
    language: str = "ar",
) -> WorkforceIdentity:
    normalized_email = str(email or "").strip().lower()
    normalized_first = " ".join(str(first_name or "").split())
    normalized_last = " ".join(str(last_name or "").split())
    normalized_language = str(language or "ar").strip().lower()

    if not _EMAIL_PATTERN.match(normalized_email):
        raise ValueError("A valid user email is required.")
    if not normalized_first:
        raise ValueError("First name is required.")
    if len(normalized_first) > 140 or len(normalized_last) > 140:
        raise ValueError("User name is too long.")
    if normalized_language not in SUPPORTED_LANGUAGES:
        raise ValueError("Unsupported user language.")

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
        raise ValueError("User roles must be a list.")
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_role in roles:
        role = str(raw_role or "").strip()
        if not role:
            raise ValueError("User roles cannot contain an empty value.")
        if role in seen:
            continue
        seen.add(role)
        normalized.append(role)
    if len(normalized) > MAX_USER_ROLES:
        raise ValueError(f"A user cannot have more than {MAX_USER_ROLES} roles.")
    return tuple(normalized)


def validate_temporary_password(password: str, *, email: str = "") -> str:
    value = str(password or "")
    if len(value) < 10:
        raise ValueError("Temporary password must contain at least 10 characters.")
    if not any(character.isalpha() for character in value):
        raise ValueError("Temporary password must contain at least one letter.")
    if not any(character.isdigit() for character in value):
        raise ValueError("Temporary password must contain at least one number.")
    local_part = str(email or "").split("@", 1)[0].strip().lower()
    if local_part and len(local_part) >= 4 and local_part in value.lower():
        raise ValueError("Temporary password must not contain the email name.")
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
    "MAX_USER_ROLES",
    "SUPPORTED_LANGUAGES",
    "WorkforceIdentity",
    "audit_snapshot",
    "normalize_identity",
    "normalize_role_selection",
    "validate_temporary_password",
]
