from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint

from almdina_erp.almdina_erp.infrastructure.frappe.factory_user_scope import (
    ALMDINA_APP,
    is_almdina_user,
)


def current_user() -> str:
    return str(frappe.session.user)


def roles_of(user: str | None = None) -> tuple[str, ...]:
    actor = str(user or current_user() or "").strip()
    if not actor:
        return ()
    return tuple(str(role) for role in frappe.get_roles(actor) if role)


def assert_enabled_user_has_role(user: str, role: str) -> None:
    """Ensure an assignee is an active Almdina worker in the configured role."""

    resolved_user = str(user or "").strip()
    resolved_role = str(role or "").strip()
    if not resolved_user:
        frappe.throw(_("اختر عاملًا لإسناد المرحلة إليه."))
    if resolved_user in {"Guest", "Administrator"}:
        frappe.throw(_("لا يمكن إسناد مرحلة إنتاج إلى هذا الحساب النظامي."))
    if not resolved_role:
        frappe.throw(_("مرحلة الإنتاج لا تحتوي على دور تشغيلي محدد."))
    if not frappe.db.exists("Role", resolved_role):
        frappe.throw(_("الدور التشغيلي {0} غير موجود.").format(resolved_role))
    if not frappe.db.exists("User", resolved_user):
        frappe.throw(_("المستخدم {0} غير موجود.").format(resolved_user))

    user_row = frappe.db.get_value(
        "User",
        resolved_user,
        ["enabled", "user_type", "default_app"],
        as_dict=True,
    )
    if not user_row or not cint(user_row.enabled):
        frappe.throw(_("المستخدم {0} غير مفعّل.").format(resolved_user))
    if str(user_row.user_type or "") != "System User":
        frappe.throw(_("يمكن إسناد مراحل الإنتاج إلى مستخدمي النظام فقط."))
    if not is_almdina_user(str(user_row.default_app or "")):
        frappe.throw(
            _("المستخدم {0} غير مضاف إلى مستخدمي معمل Almdina.").format(
                resolved_user
            )
        )

    user_roles = set(frappe.get_roles(resolved_user))
    if resolved_role not in user_roles:
        frappe.throw(
            _("المستخدم {0} لا يملك الدور التشغيلي {1} المطلوب لهذه المرحلة.").format(
                resolved_user,
                resolved_role,
            )
        )


def get_users_for_role(role: str) -> list[dict[str, str]]:
    resolved_role = str(role or "").strip()
    if not resolved_role or not frappe.db.exists("Role", resolved_role):
        return []
    rows = frappe.db.sql(
        """
        select u.name, u.full_name
          from `tabUser` u
          inner join `tabHas Role` hr on hr.parent = u.name
         where hr.role = %s
           and u.enabled = 1
           and u.user_type = 'System User'
           and coalesce(u.default_app, '') = %s
           and u.name not in ('Guest', 'Administrator')
         order by u.full_name asc, u.name asc
        """,
        (resolved_role, ALMDINA_APP),
        as_dict=True,
    )
    return [
        {"name": row.name, "full_name": row.full_name or row.name}
        for row in rows
    ]


__all__ = [
    "assert_enabled_user_has_role",
    "current_user",
    "get_users_for_role",
]
