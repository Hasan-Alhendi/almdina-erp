from __future__ import annotations

from typing import Any

from almdina_erp.almdina_erp.domain.security.workforce import profile_for_key
from almdina_erp.almdina_erp.infrastructure.frappe.workforce_repository import (
    FrappeWorkforceRepository,
)
from almdina_erp.almdina_erp.services.workforce_service import (
    create_workforce_user,
    reset_workforce_password,
    update_workforce_user,
)


_repository = FrappeWorkforceRepository()


def provision_user(
    email: str,
    profile: str,
    first_name: str,
    last_name: str = "",
    temporary_password: str | None = None,
    language: str = "ar",
) -> dict[str, Any]:
    """Compatibility command used by explicit seed operations."""

    user_name = str(email or "").strip().lower()
    created = not _repository.user_exists(user_name)
    data = {
        "email": user_name,
        "profile": profile,
        "first_name": first_name,
        "last_name": last_name,
        "temporary_password": temporary_password,
        "language": language,
    }
    if created:
        create_workforce_user(data)
    else:
        update_workforce_user(
            user_name,
            {
                "profile": profile,
                "first_name": first_name,
                "last_name": last_name,
                "language": language,
            },
        )
        reset_workforce_password(user_name, str(temporary_password or ""))

    selected = profile_for_key(profile)
    return {
        "email": user_name,
        "profile": profile,
        "created": created,
        "roles_added": [],
        "default_workspace": selected.default_workspace,
        "default_app": selected.default_app,
    }


__all__ = ["provision_user"]
