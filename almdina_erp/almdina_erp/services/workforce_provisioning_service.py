from __future__ import annotations

from collections.abc import Sequence
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


def provision_user(
    email: str,
    roles: Sequence[str],
    first_name: str,
    last_name: str = "",
    temporary_password: str | None = None,
    language: str = "ar",
) -> dict[str, Any]:
    """Provision an Almdina account with explicit roles and no implicit profile."""

    user_name = str(email or "").strip().lower()
    selected_roles = list(roles or ())
    created = not _repository.user_exists(user_name)
    data = {
        "email": user_name,
        "roles": selected_roles,
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
                "roles": selected_roles,
                "first_name": first_name,
                "last_name": last_name,
                "language": language,
            },
        )
        if temporary_password:
            reset_workforce_password(user_name, str(temporary_password))

    return {
        "email": user_name,
        "created": created,
        "roles": selected_roles,
        "default_workspace": "Almdina ERP",
        "default_app": "almdina_erp",
    }


__all__ = ["provision_user"]
