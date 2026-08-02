from __future__ import annotations

from typing import Any

from almdina_erp.almdina_erp.domain.security.workforce import (
    PROFILES,
    OperationalProfile as UserProfile,
)


def provision_user(
    email: str,
    profile: str,
    first_name: str,
    last_name: str = "",
    temporary_password: str | None = None,
    language: str = "ar",
) -> dict[str, Any]:
    """Delegate the legacy seed command to the secured workforce service."""

    from almdina_erp.almdina_erp.services.workforce_provisioning_service import (
        provision_user as execute,
    )

    return execute(
        email=email,
        profile=profile,
        first_name=first_name,
        last_name=last_name,
        temporary_password=temporary_password,
        language=language,
    )


__all__ = ["PROFILES", "UserProfile", "provision_user"]
