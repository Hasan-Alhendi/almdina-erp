from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from almdina_erp.almdina_erp.infrastructure.frappe.permission_matrix_repository import (
    FrappePermissionMatrixRepository,
)
from almdina_erp.almdina_erp.infrastructure.frappe.supporting_doctype_permission_repository import (
    SupportingDoctypePermissionRepository,
)
from almdina_erp.almdina_erp.infrastructure.frappe.system_role_policy import (
    PROTECTED_SYSTEM_ROLES,
)


class ProjectedPermissionMatrixRepository(FrappePermissionMatrixRepository):
    """Canonical matrix repository plus native grants for related Frappe records."""

    def __init__(self) -> None:
        super().__init__()
        self._supporting = SupportingDoctypePermissionRepository()

    def list_roles(self) -> list[dict[str, Any]]:
        """Expose only roles that may carry explicit Almdina business authority."""

        return [
            row
            for row in super().list_roles()
            if str(row.get("name") or "") not in PROTECTED_SYSTEM_ROLES
        ]

    def validate_role(self, role: str) -> str:
        resolved = str(role or "").strip()
        if resolved in PROTECTED_SYSTEM_ROLES:
            raise ValueError("Select an editable system role.")
        return super().validate_role(resolved)

    def save_role_states(
        self,
        role_states: Mapping[str, Mapping[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        saved = super().save_role_states(role_states)
        for role, snapshot in saved.items():
            self._supporting.save_role_state(
                role,
                snapshot["capabilities"],
            )
        return saved


__all__ = ["ProjectedPermissionMatrixRepository"]
