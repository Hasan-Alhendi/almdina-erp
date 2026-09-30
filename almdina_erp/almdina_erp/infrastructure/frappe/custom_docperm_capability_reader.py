from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import frappe

from almdina_erp.almdina_erp.application.security.business_capability_state import (
    normalize_business_capability_state,
)
from almdina_erp.almdina_erp.domain.security.authorization import (
    ALL_CAPABILITIES,
    CAPABILITY_CATALOG,
)
from almdina_erp.almdina_erp.infrastructure.frappe.system_role_policy import (
    PROTECTED_SYSTEM_ROLES,
)


def _definitions_by_doctype() -> dict[str, list[tuple[str, Any]]]:
    grouped: dict[str, list[tuple[str, Any]]] = {}
    for capability, definition in CAPABILITY_CATALOG.items():
        grouped.setdefault(definition.applies_to, []).append((capability, definition))
    return grouped


_DEFINITIONS_BY_DOCTYPE = _definitions_by_doctype()


class CustomDocPermCapabilityReader:
    """Read factory capability grants from Custom DocPerm columns.

    This is the Frappe-native grant reader used for parity and, after cutover,
    runtime authority. Capability authority is column-based only: protected
    system roles are rejected, missing rows deny all, and native document
    permission helpers are never used as a substitute grant source.
    """

    def validate_role(self, role: str) -> str:
        resolved = str(role or "").strip()
        if not resolved or resolved in PROTECTED_SYSTEM_ROLES:
            raise ValueError("Select an editable system role.")
        if not frappe.db.exists("Role", resolved):
            raise ValueError(f"Role {resolved} does not exist.")
        return resolved

    def role_capabilities(self, role: str) -> dict[str, bool]:
        """Return normalized business capabilities for one editable role."""

        resolved = self.validate_role(role)
        raw = {capability: False for capability in ALL_CAPABILITIES}
        meta = frappe.get_meta("Custom DocPerm")

        for doctype, definitions in _DEFINITIONS_BY_DOCTYPE.items():
            fields = [
                definition.permission_type
                for _, definition in definitions
                if meta.has_field(definition.permission_type)
            ]
            if not fields:
                continue
            rows = frappe.get_all(
                "Custom DocPerm",
                filters={
                    "parent": doctype,
                    "role": resolved,
                    "permlevel": 0,
                    "if_owner": 0,
                },
                fields=fields,
            )
            if not rows:
                continue
            for capability, definition in definitions:
                fieldname = definition.permission_type
                if fieldname not in fields:
                    continue
                if any(bool(row.get(fieldname)) for row in rows):
                    raw[capability] = True

        return normalize_business_capability_state(raw)

    def role_state(self, role: str) -> dict[str, Any]:
        resolved = self.validate_role(role)
        capabilities = self.role_capabilities(resolved)
        return {
            "role": resolved,
            "capabilities": capabilities,
            "source_by_doctype": {
                doctype: "custom_docperm" for doctype in sorted(_DEFINITIONS_BY_DOCTYPE)
            },
        }

    def granted_capabilities_for_roles(self, roles: Mapping[str, Any] | list[str]) -> frozenset[str]:
        """Union capability grants across editable roles only."""

        granted: set[str] = set()
        for role in roles:
            resolved = str(role or "").strip()
            if not resolved or resolved in PROTECTED_SYSTEM_ROLES:
                continue
            try:
                state = self.role_capabilities(resolved)
            except ValueError:
                continue
            granted.update(
                capability
                for capability, enabled in state.items()
                if enabled is True
            )
        return frozenset(granted)


__all__ = ["CustomDocPermCapabilityReader"]
