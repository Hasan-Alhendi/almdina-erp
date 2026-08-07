from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from almdina_erp.almdina_erp.infrastructure.frappe.permission_matrix_repository import (
    FrappePermissionMatrixRepository,
)
from almdina_erp.almdina_erp.infrastructure.frappe.supporting_doctype_permission_repository import (
    SupportingDoctypePermissionRepository,
)


class ProjectedPermissionMatrixRepository(FrappePermissionMatrixRepository):
    """Canonical matrix repository plus native grants for related Frappe records."""

    def __init__(self) -> None:
        super().__init__()
        self._supporting = SupportingDoctypePermissionRepository()

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
