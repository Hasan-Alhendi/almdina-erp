from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from almdina_erp.almdina_erp.infrastructure.frappe.workforce_repository import (
    FrappeWorkforceRepository,
)
from almdina_erp.almdina_erp.services.workforce_service import (
    create_workforce_user,
    reset_workforce_password,
    update_workforce_user,
)


_repository = FrappeWorkforceRepository()


def _normalize_roles(roles: Iterable[str] | str | None) -> list[str]:
    source = [roles] if isinstance(roles, str) else list(roles or ())
    return list(dict.fromkeys(str(role or "").strip() for role in source if str(role or "").strip()))


def provision_user(
    email: str,
    roles: Iterable[str] | str | None,
    first_name: str,
    last_name: str = "",
    temporary_password: str | None = None,
    language: str = "ar",
) -> dict[str, Any]:
    """Provision one Almdina user using explicit managed roles only."""

    user_name = str(email or "").strip().lower()
    selected_roles = _normalize_roles(roles)
    created = not _repository.user_exists(user_name)
    data = {
        "email": user_name,
        "roles": selected_roles,
        "first_name": first_name,
        "last_name": last_name,
        "language": language,
    }
    if temporary_password:
        data["temporary_password"] = temporary_password

    if created:
        create_workforce_user(data)
    else:
        update_workforce_user(user_name, data)
        if temporary_password:
            reset_workforce_password(user_name, str(temporary_password))

    user = _repository.get_user(user_name)
    return {
        "email": user_name,
        "created": created,
        "roles": list(user.get("workforce_roles") or ()),
        "default_workspace": str(user.get("default_workspace") or ""),
        "default_app": str(user.get("default_app") or ""),
    }


__all__ = ["provision_user"]
