from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

import frappe
from frappe.permissions import setup_custom_perms

from almdina_erp.almdina_erp.application.security.permission_matrix import (
    changed_capabilities,
    field_permission_projection,
    normalize_capability_state,
    standard_permission_projection,
    validate_capability_dependencies,
)
from almdina_erp.almdina_erp.domain.security.authorization import CAPABILITY_CATALOG
from almdina_erp.almdina_erp.domain.security.role_management import PROTECTED_ROLE_NAMES
from almdina_erp.almdina_erp.infrastructure.frappe.managed_role_registry import managed_role_names


PROTECTED_ROLES = PROTECTED_ROLE_NAMES
_IDENTITY_FIELDS = frozenset(
    {
        "name", "doctype", "parent", "parenttype", "parentfield", "idx", "owner",
        "creation", "modified", "modified_by", "docstatus", "role", "permlevel",
    }
)


def _definitions_by_doctype() -> dict[str, list[tuple[str, Any]]]:
    grouped: dict[str, list[tuple[str, Any]]] = defaultdict(list)
    for capability, definition in CAPABILITY_CATALOG.items():
        grouped[definition.applies_to].append((capability, definition))
    return dict(grouped)


_DEFINITIONS_BY_DOCTYPE = _definitions_by_doctype()


class FrappePermissionMatrixRepository:
    """Read and write explicit Almdina capability fields through Custom DocPerm."""

    def ensure_custom_permission_baseline(self, doctypes: Sequence[str] | None = None) -> None:
        selected = tuple(doctypes or _DEFINITIONS_BY_DOCTYPE)
        for doctype in selected:
            self._ensure_doctype_custom_permission_baseline(str(doctype))

    def list_roles(self) -> list[dict[str, Any]]:
        managed = sorted(managed_role_names().difference(PROTECTED_ROLES))
        if not managed:
            return []
        role_meta = frappe.get_meta("Role")
        fields = ["name", "desk_access"]
        if role_meta.has_field("disabled"):
            fields.append("disabled")
        rows = frappe.get_all(
            "Role",
            filters={"name": ["in", managed]},
            fields=fields,
            order_by="name asc",
            limit_page_length=0,
        )
        return [
            {"name": str(row.name), "desk_access": bool(row.get("desk_access"))}
            for row in rows
            if not bool(row.get("disabled"))
        ]

    def validate_role(self, role: str) -> str:
        resolved = str(role or "").strip()
        if not resolved or resolved in PROTECTED_ROLES:
            raise ValueError("Select an editable Almdina role.")
        if not frappe.db.exists("Role", resolved):
            raise ValueError(f"Role {resolved} does not exist.")
        if resolved not in managed_role_names():
            raise ValueError("This role is outside the Almdina managed-role registry.")
        return resolved

    def role_state(self, role: str) -> dict[str, Any]:
        resolved = self.validate_role(role)
        state = {capability: False for capability in sorted(CAPABILITY_CATALOG)}
        source_by_doctype: dict[str, str] = {}
        for doctype, definitions in _DEFINITIONS_BY_DOCTYPE.items():
            rows, source = self._effective_rows(doctype, resolved, definitions)
            source_by_doctype[doctype] = source
            for capability, definition in definitions:
                state[capability] = any(bool(row.get(definition.permission_type)) for row in rows)
        return {
            "role": resolved,
            "capabilities": normalize_capability_state(state),
            "source_by_doctype": source_by_doctype,
        }

    def role_states(self, roles: Sequence[str] | None = None) -> dict[str, dict[str, bool]]:
        selected = (
            [self.validate_role(role) for role in roles]
            if roles is not None
            else [str(row["name"]) for row in self.list_roles()]
        )
        return {role: self.role_state(role)["capabilities"] for role in sorted(dict.fromkeys(selected))}

    def save_role_state(self, role: str, capabilities: Mapping[str, Any]) -> dict[str, Any]:
        resolved = self.validate_role(role)
        return self.save_role_states({resolved: capabilities})[resolved]

    def save_role_states(
        self,
        role_states: Mapping[str, Mapping[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        """Persist explicit role matrices atomically after dependency validation."""

        prepared: dict[str, dict[str, bool]] = {}
        for role, state in role_states.items():
            resolved = self.validate_role(role)
            if resolved in prepared:
                raise ValueError(f"Duplicate role state: {resolved}")
            prepared[resolved] = validate_capability_dependencies(state)
        if not prepared:
            raise ValueError("At least one role state is required.")

        for role in sorted(prepared):
            frappe.db.sql("select name from `tabRole` where name = %s for update", (role,))
        self.ensure_custom_permission_baseline(tuple(_DEFINITIONS_BY_DOCTYPE))
        for role in sorted(prepared):
            desired = prepared[role]
            for doctype, definitions in _DEFINITIONS_BY_DOCTYPE.items():
                self._save_doctype_state(doctype, role, definitions, desired)
                self._save_field_permission_state(doctype, role, desired)
        for role in sorted(prepared):
            self.clear_role_cache(role)
        return {role: self.role_state(role) for role in sorted(prepared)}

    def record_audit(
        self,
        *,
        role: str,
        before: Mapping[str, Any],
        after: Mapping[str, Any],
        changed_by: str,
        source: str = "Almdina Permission Console",
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
                "source": str(source or "Almdina Permission Console"),
                "change_count": len(changes),
                "changed_capabilities": ", ".join(change["key"] for change in changes),
                "before_json": json.dumps(normalize_capability_state(before), ensure_ascii=False, sort_keys=True),
                "after_json": json.dumps(normalize_capability_state(after), ensure_ascii=False, sort_keys=True),
            }
        ).insert(ignore_permissions=True)
        return str(document.name)

    def list_audit(self, role: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        filters = {"role": self.validate_role(role)} if role else None
        rows = frappe.get_all(
            "Almdina Permission Audit",
            filters=filters,
            fields=["name", "role", "changed_by", "changed_on", "source", "change_count", "changed_capabilities"],
            order_by="changed_on desc",
            limit=max(1, min(int(limit or 20), 100)),
        )
        return [dict(row) for row in rows]

    @staticmethod
    def user_roles(user: str) -> frozenset[str]:
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
        request_cache = getattr(frappe.local, "almdina_matrix_capabilities", None)
        for user in users:
            if request_cache is not None:
                request_cache.pop(str(user), None)
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
            filters={"parent": doctype, "role": role, "permlevel": 0, "if_owner": 0},
            fields=fields,
            order_by="creation asc",
        )
        if custom or frappe.db.exists("Custom DocPerm", {"parent": doctype}):
            return [dict(row) for row in custom], "custom"
        fields = self._available_fields("DocPerm", definitions)
        standard = frappe.get_all(
            "DocPerm",
            filters={"parent": doctype, "role": role, "permlevel": 0, "if_owner": 0},
            fields=fields,
            order_by="idx asc",
        )
        return [dict(row) for row in standard], "standard" if standard else "none"

    @staticmethod
    def _available_fields(
        permission_doctype: str,
        definitions: list[tuple[str, Any]],
    ) -> list[str]:
        meta = frappe.get_meta(permission_doctype)
        requested = ["name", "read", "create", "write", "delete"] + [
            definition.permission_type for _, definition in definitions
        ]
        return [field for field in dict.fromkeys(requested) if meta.has_field(field)]

    def _new_override_documents(self, doctype: str, role: str) -> list[Any]:
        standard_names = frappe.get_all(
            "DocPerm",
            filters={"parent": doctype, "role": role, "permlevel": 0, "if_owner": 0},
            pluck="name",
            order_by="idx asc",
        )
        if not standard_names:
            return [self._blank_override(doctype, role)]
        return [self._override_from_standard(doctype, str(name)) for name in standard_names]

    def _ensure_doctype_custom_permission_baseline(self, doctype: str) -> None:
        standard_rows = frappe.get_all(
            "DocPerm",
            filters={"parent": doctype},
            fields=["name", "role", "permlevel", "if_owner"],
            order_by="idx asc",
        )
        if not standard_rows:
            return
        if not frappe.db.exists("Custom DocPerm", {"parent": doctype}):
            setup_custom_perms(doctype)
            return
        custom_rows = frappe.get_all(
            "Custom DocPerm",
            filters={"parent": doctype},
            fields=["role", "permlevel", "if_owner"],
        )
        existing = Counter(self._permission_identity(row) for row in custom_rows)
        required = Counter(self._permission_identity(row) for row in standard_rows)
        missing = required - existing
        if not missing:
            return
        for row in standard_rows:
            identity = self._permission_identity(row)
            if missing[identity] <= 0:
                continue
            document = self._override_from_standard(doctype, str(row.get("name")))
            document.insert(ignore_permissions=True)
            missing[identity] -= 1

    @staticmethod
    def _permission_identity(row: Mapping[str, Any] | Any) -> tuple[str, int, int]:
        return (
            str(row.get("role") or ""),
            int(row.get("permlevel") or 0),
            int(bool(row.get("if_owner"))),
        )

    @staticmethod
    def _override_from_standard(doctype: str, name: str) -> Any:
        standard = frappe.get_doc("DocPerm", name)
        custom_meta = frappe.get_meta("Custom DocPerm")
        payload: dict[str, Any] = {
            "doctype": "Custom DocPerm",
            "parent": doctype,
            "parenttype": "DocType",
            "parentfield": "permissions",
            "role": standard.role,
            "permlevel": int(standard.permlevel or 0),
        }
        for field in custom_meta.fields:
            fieldname = str(field.fieldname or "")
            if not fieldname or fieldname in _IDENTITY_FIELDS:
                continue
            if standard.meta.has_field(fieldname):
                payload[fieldname] = standard.get(fieldname)
        return frappe.get_doc(payload)

    @staticmethod
    def _blank_override(doctype: str, role: str, permlevel: int = 0) -> Any:
        return frappe.get_doc(
            {
                "doctype": "Custom DocPerm",
                "parent": doctype,
                "parenttype": "DocType",
                "parentfield": "permissions",
                "role": role,
                "permlevel": int(permlevel),
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
            filters={"parent": doctype, "role": role, "permlevel": 0, "if_owner": 0},
            pluck="name",
            order_by="creation asc",
        )
        has_standard = bool(
            frappe.db.exists(
                "DocPerm",
                {"parent": doctype, "role": role, "permlevel": 0, "if_owner": 0},
            )
        )
        any_enabled = any(desired[capability] for capability, _ in definitions)
        if not row_names and not any_enabled and not has_standard:
            return
        documents = [frappe.get_doc("Custom DocPerm", name) for name in row_names] or self._new_override_documents(doctype, role)
        standard_rights = standard_permission_projection(doctype, desired)
        for document in documents:
            for capability, definition in definitions:
                if document.meta.has_field(definition.permission_type):
                    document.set(definition.permission_type, int(bool(desired[capability])))
            for permission_type, enabled in standard_rights.items():
                if document.meta.has_field(permission_type):
                    document.set(permission_type, int(bool(enabled)))
            if document.is_new():
                document.insert(ignore_permissions=True)
            else:
                document.save(ignore_permissions=True)

    def _save_field_permission_state(
        self,
        doctype: str,
        role: str,
        desired: Mapping[str, bool],
    ) -> None:
        for permlevel, rights in field_permission_projection(doctype, desired).items():
            row_names = frappe.get_all(
                "Custom DocPerm",
                filters={"parent": doctype, "role": role, "permlevel": permlevel, "if_owner": 0},
                pluck="name",
                order_by="creation asc",
            )
            enabled = any(bool(value) for value in rights.values())
            if not row_names and not enabled:
                continue
            documents = [frappe.get_doc("Custom DocPerm", name) for name in row_names]
            if not documents:
                documents = [self._blank_override(doctype, role, permlevel)]
            for document in documents:
                for permission_type, value in rights.items():
                    if document.meta.has_field(permission_type):
                        document.set(permission_type, int(bool(value)))
                if document.is_new():
                    document.insert(ignore_permissions=True)
                else:
                    document.save(ignore_permissions=True)


__all__ = ["FrappePermissionMatrixRepository", "PROTECTED_ROLES"]
