from __future__ import annotations

from collections.abc import Iterable
from typing import Any


def provision_user(
    email: str,
    roles: Iterable[str] | str | None,
    first_name: str,
    last_name: str = "",
    temporary_password: str | None = None,
    language: str = "ar",
) -> dict[str, Any]:
    """Delegate explicit role-based provisioning to the secured workforce service."""

    from almdina_erp.almdina_erp.services.workforce_provisioning_service import (
        provision_user as execute,
    )

    return execute(
        email=email,
        roles=roles,
        first_name=first_name,
        last_name=last_name,
        temporary_password=temporary_password,
        language=language,
    )


__all__ = ["provision_user"]
