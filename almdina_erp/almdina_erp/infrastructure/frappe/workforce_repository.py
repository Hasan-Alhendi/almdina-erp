from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

import frappe
from frappe.utils import cint
from frappe.utils.password import update_password

from almdina_erp.almdina_erp.application.security.workforce_management import (
    WorkforceIdentity,
    audit_snapshot,
    normalize_role_selection,
)
from almdina_erp.almdina_erp.infrastructure.frappe.system_role_policy import (
    PROTECTED_SYSTEM_ROLES,
)


# Workforce role assignment follows the same protected system-role policy used
# by the permission matrix and authorization gateway.
PROTECTED_ASSIGNMENT_ROLES = PROTECTED_SYSTEM_ROLES


class FrappeWorkforceRepository:
    """Persistence adapter for Almdina users and their direct Frappe roles."""

    @staticmethod
    def _roles_for_user(user: str) -> tuple[str, ...]:
        return tuple(
            str(role)
            for role in frappe.get_all(
                "Has Role",
                filters={"parent": user, "parenttype": "User"},
                pluck="role",
                order_by="role asc",
            )
            if role
        )

    @staticmethod
    def _assignable_roles(roles: Sequence[str]) -> tuple[str, ...]:
        return tuple(
            role for role in roles if role not in PROTECTED_ASSIGNMENT_ROLES
        )

    @staticmethod
    def _is_almdina_user(*, default_app: str) -> bool:
        return default_app == "almdina_erp"

    def lock_user(self, user: str) -> None:
        frappe.db.sql(
            "select name from `tabUser` where name = %s for update",
            (user,),
        )

    def user_exists(self, user: str) -> bool:
        return bool(frappe.db.exists("User", user))

    def list_assignable_roles(self) -> list[dict[str, Any]]:
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
            if row.name not in PROTECTED_ASSIGNMENT_ROLES
            and not bool(row.get("disabled"))
        ]

    def validate_roles(self, roles: Sequence[str] | None) -> tuple[str, ...]:
        selected = normalize_role_selection(roles)
        catalog = {row["name"] for row in self.list_assignable_roles()}
        invalid = sorted(set(selected).difference(catalog))
        if invalid:
            raise ValueError(
                "تحتوي الأدوار المحددة على أدوار غير موجودة أو محمية ولا يمكن إسنادها: "
                + ", ".join(invalid)
            )
        return selected

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
        all_roles = self._roles_for_user(user.name)
        roles = self._assignable_roles(all_roles)
        return {
            "email": str(user.name),
            "first_name": str(user.first_name or ""),
            "last_name": str(user.last_name or ""),
            "full_name": str(user.full_name or user.name),
            "enabled": bool(cint(user.enabled)),
            "language": str(user.language or "ar"),
            "roles": list(roles),
            "default_workspace": str(user.default_workspace or ""),
            "default_app": str(user.default_app or ""),
            "last_active": str(user.last_active or ""),
            "active_assignments": self.active_assignment_count(user.name),
            "is_almdina": self._is_almdina_user(
                default_app=str(user.default_app or ""),
            ),
        }

    def get_user(self, user: str, *, require_almdina: bool = True) -> dict[str, Any]:
        if not self.user_exists(user):
            raise ValueError("المستخدم المحدد غير موجود.")
        snapshot = self._snapshot_from_doc(frappe.get_doc("User", user))
        if require_almdina and not snapshot["is_almdina"]:
            raise ValueError("هذا الحساب غير مضاف إلى نطاق مستخدمي معمل Almdina.")
        return snapshot

    def _list_user_names(
        self,
        *,
        search: str,
        enabled: bool | None,
        limit: int,
        almdina: bool,
    ) -> list[str]:
        conditions = [
            "u.user_type = 'System User'",
            "u.name not in ('Guest', 'Administrator')",
            (
                "coalesce(u.default_app, '') = 'almdina_erp'"
                if almdina
                else "coalesce(u.default_app, '') != 'almdina_erp'"
            ),
        ]
        values: list[Any] = []
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
        return [str(row.name) for row in rows]

    def list_users(
        self,
        *,
        search: str = "",
        enabled: bool | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        return [
            self.get_user(user)
            for user in self._list_user_names(
                search=search,
                enabled=enabled,
                limit=limit,
                almdina=True,
            )
        ]

    def list_available_users(
        self,
        *,
        search: str = "",
        enabled: bool | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Return System Users that exist in Frappe but are outside Almdina."""

        return [
            self.get_user(user, require_almdina=False)
            for user in self._list_user_names(
                search=search,
                enabled=enabled,
                limit=limit,
                almdina=False,
            )
        ]

    def adopt_user(self, user_name: str) -> dict[str, Any]:
        """Explicitly move an existing System User into Almdina scope.

        Existing non-protected roles are preserved to avoid destructive changes to
        ERPNext access. The platform-wide System Manager role is deliberately
        removed, while Desk User is retained/added as non-business shell access.
        No factory business role is granted by this operation.
        """

        resolved = str(user_name or "").strip().lower()
        if not resolved or resolved in {"administrator", "guest"}:
            raise ValueError("اختر مستخدم نظام صالحًا يمكن إضافته إلى مستخدمي المعمل.")
        if not self.user_exists(resolved):
            raise ValueError("المستخدم المحدد غير موجود.")

        user = frappe.get_doc("User", resolved)
        if str(user.user_type or "") != "System User":
            raise ValueError("يمكن إضافة مستخدمي النظام فقط إلى مستخدمي معمل Almdina.")
        if self._is_almdina_user(default_app=str(user.default_app or "")):
            return self.get_user(resolved)

        retained_roles = tuple(
            role
            for role in self._roles_for_user(resolved)
            if role != "System Manager"
        )
        required_roles = tuple(dict.fromkeys((*retained_roles, "Desk User")))
        user.set("roles", [])
        for role in required_roles:
            if frappe.db.exists("Role", role):
                user.append("roles", {"role": role})
        user.default_app = "almdina_erp"
        if frappe.db.exists("Workspace", "Almdina ERP"):
            user.default_workspace = "Almdina ERP"
        user.save(ignore_permissions=True)
        frappe.clear_cache(user=resolved)
        return self.get_user(resolved)

    def create_user(
        self,
        *,
        identity: WorkforceIdentity,
        roles: Sequence[str],
        temporary_password: str,
    ) -> dict[str, Any]:
        if self.user_exists(identity.email):
            raise ValueError("يوجد مستخدم مسجل مسبقًا بهذا البريد الإلكتروني.")
        selected_roles = self.validate_roles(roles)
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
                "default_workspace": "Almdina ERP",
            }
        )
        for role in ("Desk User", *selected_roles):
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
            raise ValueError("لا يمكن تغيير البريد الإلكتروني للمستخدم من شاشة إدارة مستخدمي المعمل.")
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
        roles: Sequence[str],
    ) -> dict[str, Any]:
        selected_roles = self.validate_roles(roles)
        required_roles = tuple(dict.fromkeys(("Desk User", *selected_roles)))

        user = frappe.get_doc("User", user_name)
        user.set("roles", [])
        for role in required_roles:
            if frappe.db.exists("Role", role):
                user.append("roles", {"role": role})
        user.default_app = "almdina_erp"
        if frappe.db.exists("Workspace", "Almdina ERP"):
            user.default_workspace = "Almdina ERP"
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
                "before_json": json.dumps(before_safe, ensure_ascii=False, sort_keys=True),
                "after_json": json.dumps(after_safe, ensure_ascii=False, sort_keys=True),
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


__all__ = [
    "FrappeWorkforceRepository",
    "PROTECTED_ASSIGNMENT_ROLES",
]
