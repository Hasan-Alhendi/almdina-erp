from __future__ import annotations

import json
import uuid
from collections import defaultdict
from collections.abc import Mapping
from typing import Any

import frappe
from frappe.utils import cint

from almdina_erp.almdina_erp.domain.security.role_management import (
    PROTECTED_ROLE_NAMES,
    RoleDefinition,
    normalize_role_name,
)
from almdina_erp.almdina_erp.infrastructure.frappe.routing_role_references import (
    configured_role_counts,
)


_METADATA_DOCTYPE = "Almdina Role Metadata"
_AUDIT_DOCTYPE = "Almdina Role Audit"


class FrappeRoleRepository:
    """Focused persistence adapter for dynamic Frappe roles."""

    @staticmethod
    def _doctype_exists(doctype: str) -> bool:
        return bool(frappe.db.exists("DocType", doctype))

    @staticmethod
    def _validate_role_name(role: str) -> str:
        resolved = normalize_role_name(role)
        if resolved in PROTECTED_ROLE_NAMES:
            raise ValueError(
                "This framework role is protected from the Almdina role console."
            )
        if not frappe.db.exists("Role", resolved):
            raise ValueError("Role does not exist.")
        return resolved

    def role_exists(self, role: str) -> bool:
        return bool(frappe.db.exists("Role", normalize_role_name(role)))

    def lock_role(self, role: str) -> None:
        resolved = normalize_role_name(role)
        frappe.db.sql(
            "select name from `tabRole` where name = %s for update",
            (resolved,),
        )

    @staticmethod
    def _safe_limit(limit: int, default: int = 100) -> int:
        try:
            parsed = int(limit or default)
        except (TypeError, ValueError):
            parsed = default
        return max(1, min(parsed, 200))

    def _metadata_map(self, roles: list[str]) -> dict[str, dict[str, Any]]:
        if not roles or not self._doctype_exists(_METADATA_DOCTYPE):
            return {}
        rows = frappe.get_all(
            _METADATA_DOCTYPE,
            filters={"role": ["in", roles]},
            fields=["name", "role", "role_uid", "description", "managed_by_almdina"],
        )
        return {str(row.role): dict(row) for row in rows}

    def _group_count(
        self,
        doctype: str,
        role_field: str,
        roles: list[str],
        *,
        filters: Mapping[str, Any] | None = None,
    ) -> dict[str, int]:
        if not roles or not self._doctype_exists(doctype):
            return {}
        meta = frappe.get_meta(doctype)
        if not meta.has_field(role_field):
            return {}
        conditions: dict[str, Any] = {
            role_field: ["in", roles],
            **dict(filters or {}),
        }
        rows = frappe.get_all(
            doctype,
            filters=conditions,
            fields=[role_field],
            limit_page_length=0,
        )
        counts: defaultdict[str, int] = defaultdict(int)
        for row in rows:
            role = str(row.get(role_field) or "").strip()
            if role:
                counts[role] += 1
        return dict(counts)

    @staticmethod
    def _sum_counts(*maps: Mapping[str, int]) -> dict[str, int]:
        totals: defaultdict[str, int] = defaultdict(int)
        for values in maps:
            for role, count in values.items():
                totals[str(role)] += int(count or 0)
        return dict(totals)

    def _reference_maps(self, roles: list[str]) -> dict[str, dict[str, int]]:
        assigned_users = self._group_count(
            "Has Role",
            "role",
            roles,
            filters={"parenttype": "User"},
        )
        permission_count = self._sum_counts(
            self._group_count("DocPerm", "role", roles),
            self._group_count("Custom DocPerm", "role", roles),
        )
        production_routing_references = configured_role_counts(
            "Production Routing Stage",
            roles,
        )
        workflow_references = self._sum_counts(
            self._group_count("Workflow Transition", "allowed", roles),
            self._group_count("Workflow Document State", "allow_edit", roles),
        )
        production_stage_references = configured_role_counts(
            "Production Stage",
            roles,
        )
        active_stage_references = configured_role_counts(
            "Production Stage",
            roles,
            filters={"status": ["not in", ["Completed", "Cancelled"]]},
        )
        return {
            "assigned_users": assigned_users,
            "permission_count": permission_count,
            "production_routing_references": production_routing_references,
            "workflow_references": workflow_references,
            "production_stage_references": production_stage_references,
            "active_stage_references": active_stage_references,
        }

    def _snapshots(self, rows: list[Any]) -> list[dict[str, Any]]:
        roles = [str(row.name) for row in rows]
        metadata = self._metadata_map(roles)
        references = self._reference_maps(roles)
        snapshots: list[dict[str, Any]] = []
        for row in rows:
            role = str(row.name)
            role_metadata = metadata.get(role, {})
            snapshot = {
                "name": role,
                "description": str(role_metadata.get("description") or ""),
                "role_uid": str(role_metadata.get("role_uid") or ""),
                "enabled": not bool(cint(row.get("disabled"))),
                "desk_access": bool(cint(row.get("desk_access"))),
                "is_custom": bool(cint(row.get("is_custom"))),
                "is_almdina_role": bool(
                    cint(role_metadata.get("managed_by_almdina"))
                    or cint(row.get("is_custom"))
                ),
                "created_on": str(row.get("creation") or ""),
                "modified_on": str(row.get("modified") or ""),
            }
            for key, values in references.items():
                snapshot[key] = int(values.get(role, 0) or 0)
            snapshot["reference_total"] = sum(
                int(snapshot[key] or 0)
                for key in (
                    "assigned_users",
                    "permission_count",
                    "production_routing_references",
                    "workflow_references",
                    "production_stage_references",
                )
            )
            snapshots.append(snapshot)
        return snapshots

    def list_roles(
        self,
        *,
        search: str = "",
        enabled: bool | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        filters: dict[str, Any] = {
            "name": ["not in", sorted(PROTECTED_ROLE_NAMES)],
        }
        if enabled is not None:
            filters["disabled"] = 0 if enabled else 1
        normalized_search = str(search or "").strip()
        or_filters = None
        if normalized_search:
            pattern = f"%{normalized_search}%"
            or_filters = {
                "name": ["like", pattern],
                "role_name": ["like", pattern],
            }
        rows = frappe.get_all(
            "Role",
            filters=filters,
            or_filters=or_filters,
            fields=[
                "name",
                "role_name",
                "disabled",
                "desk_access",
                "is_custom",
                "creation",
                "modified",
            ],
            order_by="disabled asc, role_name asc",
            limit_page_length=self._safe_limit(limit),
        )
        return self._snapshots(list(rows))

    def get_role(self, role: str) -> dict[str, Any]:
        resolved = self._validate_role_name(role)
        rows = frappe.get_all(
            "Role",
            filters={"name": resolved},
            fields=[
                "name",
                "role_name",
                "disabled",
                "desk_access",
                "is_custom",
                "creation",
                "modified",
            ],
            limit_page_length=1,
        )
        if not rows:
            raise ValueError("Role does not exist.")
        return self._snapshots(list(rows))[0]

    def _ensure_metadata(self, role: str, *, description: str) -> Any:
        existing = frappe.db.get_value(
            _METADATA_DOCTYPE,
            {"role": role},
            "name",
        )
        if existing:
            document = frappe.get_doc(_METADATA_DOCTYPE, existing)
            document.description = description
            document.managed_by_almdina = 1
            document.save(ignore_permissions=True)
            return document
        return frappe.get_doc(
            {
                "doctype": _METADATA_DOCTYPE,
                "role": role,
                "role_uid": str(uuid.uuid4()),
                "description": description,
                "managed_by_almdina": 1,
            }
        ).insert(ignore_permissions=True)

    def create_role(self, definition: RoleDefinition) -> dict[str, Any]:
        if self.role_exists(definition.name):
            raise ValueError("Role already exists.")
        document = frappe.get_doc(
            {
                "doctype": "Role",
                "role_name": definition.name,
                "disabled": 0 if definition.enabled else 1,
                "desk_access": 1,
                "is_custom": 1,
            }
        ).insert(ignore_permissions=True)
        self._ensure_metadata(str(document.name), description=definition.description)
        frappe.clear_cache()
        return self.get_role(str(document.name))

    def update_role(
        self,
        role: str,
        *,
        name: str,
        description: str,
    ) -> dict[str, Any]:
        current = self._validate_role_name(role)
        target = normalize_role_name(name)
        if target in PROTECTED_ROLE_NAMES:
            raise ValueError("This framework role name is protected.")
        if target != current and self.role_exists(target):
            raise ValueError("Role already exists.")

        metadata_name = frappe.db.get_value(
            _METADATA_DOCTYPE,
            {"role": current},
            "name",
        )
        if target != current:
            frappe.rename_doc("Role", current, target, force=False)
        role_document = frappe.get_doc("Role", target)
        if role_document.role_name != target:
            role_document.role_name = target
            role_document.save(ignore_permissions=True)

        if metadata_name:
            metadata = frappe.get_doc(_METADATA_DOCTYPE, metadata_name)
            metadata.role = target
            metadata.description = description
            metadata.managed_by_almdina = 1
            metadata.save(ignore_permissions=True)
        else:
            self._ensure_metadata(target, description=description)
        frappe.clear_cache()
        return self.get_role(target)

    def set_role_enabled(self, role: str, enabled: bool) -> dict[str, Any]:
        resolved = self._validate_role_name(role)
        document = frappe.get_doc("Role", resolved)
        document.disabled = 0 if enabled else 1
        document.save(ignore_permissions=True)
        frappe.clear_cache()
        return self.get_role(resolved)

    def delete_role(self, role: str) -> None:
        resolved = self._validate_role_name(role)
        metadata_name = frappe.db.get_value(
            _METADATA_DOCTYPE,
            {"role": resolved},
            "name",
        )
        if metadata_name:
            frappe.delete_doc(
                _METADATA_DOCTYPE,
                metadata_name,
                force=True,
                ignore_permissions=True,
            )
        frappe.delete_doc(
            "Role",
            resolved,
            force=False,
            ignore_permissions=True,
        )
        frappe.clear_cache()

    @staticmethod
    def _audit_snapshot(values: Mapping[str, Any] | None) -> dict[str, Any]:
        allowed = (
            "name",
            "description",
            "role_uid",
            "enabled",
            "desk_access",
            "is_custom",
            "is_almdina_role",
            "assigned_users",
            "permission_count",
            "production_routing_references",
            "workflow_references",
            "production_stage_references",
            "active_stage_references",
        )
        source = dict(values or {})
        return {key: source.get(key) for key in allowed if key in source}

    def record_audit(
        self,
        *,
        role_name: str,
        action: str,
        before: Mapping[str, Any] | None,
        after: Mapping[str, Any] | None,
        summary: str,
        changed_by: str,
    ) -> str:
        before_safe = self._audit_snapshot(before)
        after_safe = self._audit_snapshot(after)
        changed_fields = sorted(
            key
            for key in set(before_safe) | set(after_safe)
            if before_safe.get(key) != after_safe.get(key)
        )
        role_uid = str(
            after_safe.get("role_uid")
            or before_safe.get("role_uid")
            or ""
        )
        document = frappe.get_doc(
            {
                "doctype": _AUDIT_DOCTYPE,
                "role_uid": role_uid,
                "role_name": str(role_name or ""),
                "action": action,
                "changed_by": changed_by,
                "changed_on": frappe.utils.now(),
                "summary": summary,
                "changed_fields": ", ".join(changed_fields),
                "before_json": json.dumps(before_safe, ensure_ascii=False, sort_keys=True),
                "after_json": json.dumps(after_safe, ensure_ascii=False, sort_keys=True),
            }
        ).insert(ignore_permissions=True)
        return str(document.name)

    def list_audit(
        self,
        *,
        role_name: str,
        role_uid: str = "",
        limit: int = 30,
    ) -> list[dict[str, Any]]:
        filters = (
            {"role_uid": role_uid}
            if role_uid
            else {"role_name": normalize_role_name(role_name)}
        )
        rows = frappe.get_all(
            _AUDIT_DOCTYPE,
            filters=filters,
            fields=[
                "name",
                "role_name",
                "action",
                "changed_by",
                "changed_on",
                "summary",
                "changed_fields",
            ],
            order_by="changed_on desc",
            limit_page_length=self._safe_limit(limit, default=30),
        )
        return [dict(row) for row in rows]


__all__ = ["FrappeRoleRepository"]
