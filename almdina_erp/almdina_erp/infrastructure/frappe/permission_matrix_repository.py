from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Mapping
from typing import Any

import frappe

from almdina_erp.almdina_erp.application.security.permission_matrix import (
    changed_capabilities,
    normalize_capability_state,
    standard_permission_projection,
)
from almdina_erp.almdina_erp.domain.security.authorization import CAPABILITY_CATALOG


PROTECTED_ROLES = frozenset({"All", "Guest", "Desk User"})
_IDENTITY_FIELDS = frozenset(
    {
        "name",
        "doctype",
        "parent",
        "parenttype",
        "parentfield",
        "idx",
        "owner",
        "creation",
        "modified",
        "modified_by",
        "docstatus",
        "role",
        "permlevel",
    }
)


def _definitions_by_doctype() -> dict[str, list[tuple[str, Any]]]:
    grouped: dict[str, list[tuple[str, Any]]] = defaultdict(list)
    for capability, definition in CAPABILITY_CATALOG.items():
        grouped[definition.applies_to].append((capability, definition))
    return dict(grouped)


_DEFINITIONS_BY_DOCTYPE = _definitions_by_doctype()


class FrappePermissionMatrixRepository:
    """Read and write Almdina capability fields through Custom DocPerm.

    Only fields owned by the capability catalog are changed. Existing Custom
    DocPerm values outside Almdina remain untouched. When a standard DocPerm is
    overridden for the first time, all compatible non-identity permission fields
    are copied first so unrelated Frappe rights are not silently lost.
    """

    def list_roles(self) -> list[dict[str, Any]]:
        role_meta = frappe.get_meta("Role")
        fields = ["name", "desk_access"]
        if role_meta.has_field("disabled"):
            fields.append("disabled")
        rows = frappe.get_all("Role", fields=fields, order_by="name asc")
        return [
            {
                "name": str(row.name),
                "desk_access": bool(row.get("desk_access")),
            }
            for row in rows
            if row.name not in PROTECTED_ROLES and not bool(row.get("disabled"))
        ]

    def validate_role(self, role: str) -> str:
        resolved = str(role or "").strip()
        if not resolved or resolved in PROTECTED_ROLES:
            raise ValueError("Select an editable system role.")
        if not frappe.db.exists("Role", resolved):
            raise ValueError(f"Role {resolved} does not exist.")
        return resolved

    def role_state(self, role: str) -> dict[str, Any]:
        resolved = self.validate_role(role)
        state = {capability: False for capability in sorted(CAPABILITY_CATALOG)}
        source_by_doctype: dict[str, str] = {}

        for doctype, definitions in _DEFINITIONS_BY_DOCTYPE.items():
            rows, source = self._effective_rows(doctype, resolved, definitions)
            source_by_doctype[doctype] = source
            for capability, definition in definitions:
                state[capability] = any(
                    bool(row.get(definition.permission_type)) for row in rows
                )

        normalized = normalize_capability_state(state)
        return {
            "role": resolved,
            "capabilities": normalized,
            "source_by_doctype": source_by_doctype,
        }

    def save_role_state(
        self,
        role: str,
        capabilities: Mapping[str, Any],
    ) -> dict[str, Any]:
        resolved = self.validate_role(role)
        desired = normalize_capability_state(capabilities)
        frappe.db.sql(
            "select name from `tabRole` where name = %s for update",
            (resolved,),
        )

        for doctype, definitions in _DEFINITIONS_BY_DOCTYPE.items():
            self._save_doctype_state(doctype, resolved, definitions, desired)

        self.clear_role_cache(resolved)
        return self.role_state(resolved)

    def record_audit(
        self,
        *,
        role: str,
        before: Mapping[str, Any],
        after: Mapping[str, Any],
        changed_by: str,
    ) -> str | None:
        changes = changed_capabilities(before, after)
        if not changes:
            return None
        document = frappe.get_doc(
            {
                "doctype": "Almdina Permission Audit",
                "role": role,
                "changed_by": changed_by,
                "changed_on": frappe.utils.now(),
                "source": "Almdina Permission Console",
                "change_count": len(changes),
                "changed_capabilities": ", ".join(
                    change["key"] for change in changes
                ),
                "before_json": json.dumps(
                    normalize_capability_state(before),
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                "after_json": json.dumps(
                    normalize_capability_state(after),
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            }
        ).insert(ignore_permissions=True)
        return str(document.name)

    def list_audit(
        self,
        role: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        filters = {"role": self.validate_role(role)} if role else None
        rows = frappe.get_all(
            "Almdina Permission Audit",
            filters=filters,
            fields=[
                "name",
                "role",
                "changed_by",
                "changed_on",
                "change_count",
                "changed_capabilities",
            ],
            order_by="changed_on desc",
            limit_page_length=max(1, min(int(limit or 20), 100)),
        )
        return [dict(row) for row in rows]

    def user_roles(self, user: str) -> frozenset[str]:
        if user == "Administrator":
            return frozenset()
        return frozenset(frappe.get_roles(user))

    def user_has_capability_outside_role(
        self,
        *,
        user: str,
        excluded_role: str,
        capability: str,
    ) -> bool:
        for role in self.user_roles(user):
            if role == excluded_role or role in PROTECTED_ROLES:
                continue
            try:
                state = self.role_state(role)["capabilities"]
            except ValueError:
                continue
            if state.get(capability) is True:
                return True
        return False

    def clear_role_cache(self, role: str) -> None:
        for doctype in _DEFINITIONS_BY_DOCTYPE:
            frappe.clear_cache(doctype=doctype)
        users = frappe.get_all(
            "Has Role",
            filters={"role": role, "parenttype": "User"},
            pluck="parent",
        )
        for user in users:
            frappe.clear_cache(user=user)

    def _effective_rows(
        self,
        doctype: str,
        role: str,
        definitions: list[tuple[str, Any]],
    ) -> tuple[list[dict[str, Any]], str]:
        fields = self._available_fields("Custom DocPerm", definitions)
        custom = frappe.get_all(
            "Custom DocPerm",
            filters={"parent": doctype, "role": role, "permlevel": 0},
            fields=fields,
            order_by="creation asc",
        )
        if custom:
            return [dict(row) for row in custom], "custom"

        fields = self._available_fields("DocPerm", definitions)
        standard = frappe.get_all(
            "DocPerm",
            filters={"parent": doctype, "role": role, "permlevel": 0},
            fields=fields,
            order_by="idx asc",
        )
        return [dict(row) for row in standard], "standard" if standard else "none"

    def _available_fields(
        self,
        permission_doctype: str,
        definitions: list[tuple[str, Any]],
    ) -> list[str]:
        meta = frappe.get_meta(permission_doctype)
        requested = ["name", "read", "create", "write"] + [
            definition.permission_type for _, definition in definitions
        ]
        return [
            field
            for field in dict.fromkeys(requested)
            if meta.has_field(field)
        ]

    def _new_override_documents(self, doctype: str, role: str) -> list[Any]:
        standard_names = frappe.get_all(
            "DocPerm",
            filters={"parent": doctype, "role": role, "permlevel": 0},
            pluck="name",
            order_by="idx asc",
        )
        if not standard_names:
            return [self._blank_override(doctype, role)]

        custom_meta = frappe.get_meta("Custom DocPerm")
        documents: list[Any] = []
        for name in standard_names:
            standard = frappe.get_doc("DocPerm", name)
            payload: dict[str, Any] = {
                "doctype": "Custom DocPerm",
                "parent": doctype,
                "parenttype": "DocType",
                "parentfield": "permissions",
                "role": role,
                "permlevel": 0,
            }
            for field in custom_meta.fields:
                fieldname = str(field.fieldname or "")
                if not fieldname or fieldname in _IDENTITY_FIELDS:
                    continue
                if standard.meta.has_field(fieldname):
                    payload[fieldname] = standard.get(fieldname)
            documents.append(frappe.get_doc(payload))
        return documents

    @staticmethod
    def _blank_override(doctype: str, role: str) -> Any:
        return frappe.get_doc(
            {
                "doctype": "Custom DocPerm",
                "parent": doctype,
                "parenttype": "DocType",
                "parentfield": "permissions",
                "role": role,
                "permlevel": 0,
            }
        )

    def _save_doctype_state(
        self,
        doctype: str,
        role: str,
        definitions: list[tuple[str, Any]],
        desired: Mapping[str, bool],
    ) -> None:
        row_names = frappe.get_all(
            "Custom DocPerm",
            filters={"parent": doctype, "role": role, "permlevel": 0},
            pluck="name",
            order_by="creation asc",
        )
        has_standard = bool(
            frappe.db.exists(
                "DocPerm",
                {"parent": doctype, "role": role, "permlevel": 0},
            )
        )
        any_enabled = any(desired[capability] for capability, _ in definitions)
        if not row_names and not any_enabled and not has_standard:
            return

        documents = [
            frappe.get_doc("Custom DocPerm", name) for name in row_names
        ] or self._new_override_documents(doctype, role)
        standard_rights = standard_permission_projection(doctype, desired)

        for document in documents:
            for capability, definition in definitions:
                if document.meta.has_field(definition.permission_type):
                    document.set(
                        definition.permission_type,
                        int(bool(desired[capability])),
                    )

            for permission_type, enabled in standard_rights.items():
                if document.meta.has_field(permission_type):
                    document.set(permission_type, int(bool(enabled)))

            if document.is_new():
                document.insert(ignore_permissions=True)
            else:
                document.save(ignore_permissions=True)


__all__ = [
    "FrappePermissionMatrixRepository",
    "PROTECTED_ROLES",
]
