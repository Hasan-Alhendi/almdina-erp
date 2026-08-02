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
from almdina_erp.almdina_erp.domain.security.workforce import (
    MANAGED_OPERATIONAL_ROLES,
    OperationalProfile,
    infer_profile,
)


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

    @staticmethod
    def _is_almdina_user(*, default_app: str, roles: tuple[str, ...]) -> bool:
        return default_app == "almdina_erp" or bool(
            set(roles).intersection(MANAGED_OPERATIONAL_ROLES)
        )

    def lock_user(self, user: str) -> None:
        frappe.db.sql(
            "select name from `tabUser` where name = %s for update",
            (user,),
        )

    def user_exists(self, user: str) -> bool:
        return bool(frappe.db.exists("User", user))

    def ensure_profile_roles(self, profile: OperationalProfile) -> None:
        missing = [
            role for role in profile.roles if not frappe.db.exists("Role", role)
        ]
        if missing:
            raise ValueError(
                "Create the required operational roles first: "
                + ", ".join(missing)
            )

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
        profile = infer_profile(roles)
        return {
            "email": str(user.name),
            "first_name": str(user.first_name or ""),
            "last_name": str(user.last_name or ""),
            "full_name": str(user.full_name or user.name),
            "enabled": bool(cint(user.enabled)),
            "language": str(user.language or "ar"),
            "profile": profile,
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
        managed_roles = tuple(sorted(MANAGED_OPERATIONAL_ROLES))
        role_placeholders = ", ".join(["%s"] * len(managed_roles))
        conditions = [
            "u.user_type = 'System User'",
            "u.name not in ('Guest', 'Administrator')",
            "(coalesce(u.default_app, '') = 'almdina_erp' or exists ("
            "select 1 from `tabHas Role` hr "
            "where hr.parent = u.name and hr.parenttype = 'User' "
            f"and hr.role in ({role_placeholders})"
            "))",
        ]
        values: list[Any] = list(managed_roles)
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
        profile: OperationalProfile,
        temporary_password: str,
    ) -> dict[str, Any]:
        if self.user_exists(identity.email):
            raise ValueError("A user with this email already exists.")
        self.ensure_profile_roles(profile)
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
                "default_app": profile.default_app,
                "default_workspace": profile.default_workspace,
            }
        )
        for role in ("Desk User", *profile.roles):
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

    def assign_profile(
        self,
        user_name: str,
        profile: OperationalProfile,
    ) -> dict[str, Any]:
        self.ensure_profile_roles(profile)
        user = frappe.get_doc("User", user_name)
        retained = [
            row.role
            for row in (user.roles or [])
            if row.role not in MANAGED_OPERATIONAL_ROLES
        ]
        required = list(dict.fromkeys([*retained, "Desk User", *profile.roles]))
        user.set("roles", [])
        for role in required:
            if frappe.db.exists("Role", role):
                user.append("roles", {"role": role})
        user.default_app = profile.default_app
        if frappe.db.exists("Workspace", profile.default_workspace):
            user.default_workspace = profile.default_workspace
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
