from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

import frappe
from frappe.utils import cint
from frappe.utils.password import update_password

from almdina_erp.almdina_erp.application.security.workforce_management import (
    WorkforceIdentity,
    audit_snapshot,
)
from almdina_erp.almdina_erp.domain.security.role_management import (
    PROTECTED_ROLE_NAMES,
)


_ROLE_METADATA_DOCTYPE = "Almdina Role Metadata"
_DEFAULT_WORKSPACE = "Almdina ERP"


class FrappeWorkforceRepository:
    """Focused persistence adapter for Almdina workforce accounts."""

    @staticmethod
    def _roles_for_user(user: str) -> tuple[str, ...]:
        return tuple(
            frappe.get_all(
                "Has Role",
                filters={"parent": user, "parenttype": "User"},
                pluck="role",
                order_by="role asc",
            )
        )

    def _is_almdina_user(self, *, default_app: str, roles: tuple[str, ...]) -> bool:
        return default_app == "almdina_erp" or bool(
            set(roles).intersection(self.managed_role_names())
        )

    @staticmethod
    def _doctype_exists(doctype: str) -> bool:
        return bool(frappe.db.exists("DocType", doctype))

    def _metadata_map(self) -> dict[str, dict[str, Any]]:
        if not self._doctype_exists(_ROLE_METADATA_DOCTYPE):
            return {}
        rows = frappe.get_all(
            _ROLE_METADATA_DOCTYPE,
            filters={"managed_by_almdina": 1},
            fields=["role", "description", "managed_by_almdina"],
            limit_page_length=0,
        )
        return {
            str(row.role): {
                "description": str(row.description or ""),
                "managed_by_almdina": bool(cint(row.managed_by_almdina)),
            }
            for row in rows
            if str(row.role or "").strip()
        }

    def managed_role_names(self) -> frozenset[str]:
        """Roles explicitly owned by Almdina metadata.

        Historical role-name catalogues are deliberately excluded from runtime.
        A migration adopts existing Almdina roles into metadata before this
        repository becomes authoritative.
        """

        return frozenset(self._metadata_map())

    def list_assignable_roles(self) -> list[dict[str, Any]]:
        metadata = self._metadata_map()
        managed = self.managed_role_names()
        if not managed:
            return []
        rows = frappe.get_all(
            "Role",
            filters={
                "name": ["in", sorted(managed)],
                "disabled": 0,
                "desk_access": 1,
            },
            fields=["name", "role_name", "desk_access", "disabled"],
            order_by="role_name asc",
            limit_page_length=0,
        )
        return [
            {
                "name": str(row.name),
                "label": str(row.role_name or row.name),
                "description": str(metadata.get(str(row.name), {}).get("description") or ""),
            }
            for row in rows
            if str(row.name) not in PROTECTED_ROLE_NAMES
        ]

    def ensure_assignable_roles(self, roles: tuple[str, ...]) -> None:
        assignable = {row["name"] for row in self.list_assignable_roles()}
        missing = sorted(set(roles).difference(assignable))
        if missing:
            raise ValueError(
                "These roles are missing, disabled, lack Desk Access, or are not managed by Almdina: "
                + ", ".join(missing)
            )

    def lock_user(self, user: str) -> None:
        frappe.db.sql(
            "select name from `tabUser` where name = %s for update",
            (user,),
        )

    def user_exists(self, user: str) -> bool:
        return bool(frappe.db.exists("User", user))

    def active_assignment_count(self, user: str) -> int:
        return int(
            frappe.db.count(
                "Production Stage",
                {
                    "assigned_to": user,
                    "status": ["not in", ["Completed", "Cancelled"]],
                },
            )
            or 0
        )

    def _snapshot_from_doc(self, user: Any) -> dict[str, Any]:
        roles = self._roles_for_user(user.name)
        managed_roles = self.managed_role_names()
        workforce_roles = tuple(role for role in roles if role in managed_roles)
        return {
            "email": str(user.name),
            "first_name": str(user.first_name or ""),
            "last_name": str(user.last_name or ""),
            "full_name": str(user.full_name or user.name),
            "enabled": bool(cint(user.enabled)),
            "language": str(user.language or "ar"),
            "roles": list(roles),
            "workforce_roles": list(workforce_roles),
            "default_workspace": str(user.default_workspace or ""),
            "default_app": str(user.default_app or ""),
            "last_active": str(user.last_active or ""),
            "active_assignments": self.active_assignment_count(user.name),
            "is_almdina": self._is_almdina_user(
                default_app=str(user.default_app or ""),
                roles=roles,
            ),
        }

    def get_user(self, user: str, *, require_almdina: bool = True) -> dict[str, Any]:
        if not self.user_exists(user):
            raise ValueError("User does not exist.")
        snapshot = self._snapshot_from_doc(frappe.get_doc("User", user))
        if require_almdina and not snapshot["is_almdina"]:
            raise ValueError("This account is outside the Almdina workforce scope.")
        return snapshot

    def list_users(
        self,
        *,
        search: str = "",
        enabled: bool | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        managed_roles = tuple(sorted(self.managed_role_names()))
        conditions = [
            "u.user_type = 'System User'",
            "u.name not in ('Guest', 'Administrator')",
        ]
        values: list[Any] = []
        scope_conditions = ["coalesce(u.default_app, '') = 'almdina_erp'"]
        if managed_roles:
            role_placeholders = ", ".join(["%s"] * len(managed_roles))
            scope_conditions.append(
                "exists (select 1 from `tabHas Role` hr "
                "where hr.parent = u.name and hr.parenttype = 'User' "
                f"and hr.role in ({role_placeholders}))"
            )
            values.extend(managed_roles)
        conditions.append(f"({' or '.join(scope_conditions)})")

        normalized_search = str(search or "").strip()
        if normalized_search:
            pattern = f"%{normalized_search}%"
            conditions.append(
                "(u.name like %s or u.full_name like %s "
                "or u.first_name like %s or u.last_name like %s)"
            )
            values.extend([pattern, pattern, pattern, pattern])
        if enabled is not None:
            conditions.append("u.enabled = %s")
            values.append(1 if enabled else 0)
        safe_limit = max(1, min(int(limit or 100), 200))
        values.append(safe_limit)
        rows = frappe.db.sql(
            f"""
            select u.name
              from `tabUser` u
             where {' and '.join(conditions)}
             order by u.enabled desc, u.full_name asc, u.name asc
             limit %s
            """,
            tuple(values),
            as_dict=True,
        )
        return [self.get_user(str(row.name)) for row in rows]

    def create_user(
        self,
        *,
        identity: WorkforceIdentity,
        roles: tuple[str, ...],
        temporary_password: str,
    ) -> dict[str, Any]:
        if self.user_exists(identity.email):
            raise ValueError("A user with this email already exists.")
        self.ensure_assignable_roles(roles)
        user = frappe.get_doc(
            {
                "doctype": "User",
                "email": identity.email,
                "first_name": identity.first_name,
                "last_name": identity.last_name,
                "send_welcome_email": 0,
                "user_type": "System User",
                "language": identity.language,
                "enabled": 1,
                "default_app": "almdina_erp",
                "default_workspace": _DEFAULT_WORKSPACE,
            }
        )
        for role in dict.fromkeys(("Desk User", *roles)):
            if frappe.db.exists("Role", role):
                user.append("roles", {"role": role})
        user.flags.ignore_permissions = True
        user.insert(ignore_permissions=True)
        update_password(identity.email, temporary_password)
        frappe.clear_cache(user=identity.email)
        return self.get_user(identity.email)

    def update_identity(
        self,
        user_name: str,
        identity: WorkforceIdentity,
    ) -> dict[str, Any]:
        if identity.email != user_name:
            raise ValueError("User email cannot be changed from this console.")
        user = frappe.get_doc("User", user_name)
        user.first_name = identity.first_name
        user.last_name = identity.last_name
        user.language = identity.language
        user.save(ignore_permissions=True)
        frappe.clear_cache(user=user_name)
        return self.get_user(user_name)

    def assign_roles(
        self,
        user_name: str,
        roles: tuple[str, ...],
    ) -> dict[str, Any]:
        self.ensure_assignable_roles(roles)
        managed_roles = self.managed_role_names()
        user = frappe.get_doc("User", user_name)
        retained = [
            row.role
            for row in (user.roles or [])
            if row.role not in managed_roles
        ]
        required = list(dict.fromkeys([*retained, "Desk User", *roles]))
        user.set("roles", [])
        for role in required:
            if frappe.db.exists("Role", role):
                user.append("roles", {"role": role})
        user.default_app = "almdina_erp"
        if frappe.db.exists("Workspace", _DEFAULT_WORKSPACE):
            user.default_workspace = _DEFAULT_WORKSPACE
        user.save(ignore_permissions=True)
        frappe.clear_cache(user=user_name)
        return self.get_user(user_name)

    def set_enabled(self, user_name: str, enabled: bool) -> dict[str, Any]:
        frappe.db.set_value(
            "User",
            user_name,
            "enabled",
            1 if enabled else 0,
            update_modified=True,
        )
        frappe.clear_cache(user=user_name)
        return self.get_user(user_name)

    def reset_password(self, user_name: str, temporary_password: str) -> None:
        update_password(user_name, temporary_password)
        frappe.clear_cache(user=user_name)

    def record_audit(
        self,
        *,
        user_name: str,
        action: str,
        before: Mapping[str, Any] | None,
        after: Mapping[str, Any] | None,
        summary: str,
        changed_by: str,
    ) -> str:
        before_safe = audit_snapshot(dict(before or {}))
        after_safe = audit_snapshot(dict(after or {}))
        changed_fields = sorted(
            key
            for key in set(before_safe) | set(after_safe)
            if before_safe.get(key) != after_safe.get(key)
        )
        audit = frappe.get_doc(
            {
                "doctype": "Almdina User Audit",
                "target_user": user_name,
                "action": action,
                "changed_by": changed_by,
                "changed_on": frappe.utils.now(),
                "summary": summary,
                "changed_fields": ", ".join(changed_fields),
                "before_json": json.dumps(
                    before_safe,
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                "after_json": json.dumps(
                    after_safe,
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            }
        ).insert(ignore_permissions=True)
        return str(audit.name)

    def list_audit(self, user_name: str, *, limit: int = 30) -> list[dict[str, Any]]:
        safe_limit = max(1, min(int(limit or 30), 100))
        rows = frappe.get_all(
            "Almdina User Audit",
            filters={"target_user": user_name},
            fields=["name", "action", "changed_by", "changed_on", "summary", "changed_fields"],
            order_by="changed_on desc",
            limit_page_length=safe_limit,
        )
        return [dict(row) for row in rows]


__all__ = ["FrappeWorkforceRepository"]
