from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import cint


STAGE_ROLE_BY_TYPE: dict[str, str] = {
    "Sharyoun": "عامل شريون",
    "Drawing": "عامل رسم",
    "CNC": "عامل CNC",
    "Sanding": "عامل تقشيط",
}

DISPATCH_ROLES = ("Order Entry", "Production Manager")
ADMIN_ROLES = ("Order Entry", "Production Manager", "System Manager")
STAGE_ADMIN_ROLES = frozenset({"Production Manager", "System Manager"})


def current_user() -> str:
    return str(frappe.session.user)


def require_roles(*roles: str) -> None:
    user_roles = set(frappe.get_roles())
    if "System Manager" in user_roles:
        return
    if not user_roles.intersection(roles):
        frappe.throw(
            _("You do not have permission for this operation."),
            frappe.PermissionError,
        )


def assert_enabled_user_has_stage_role(user: str, stage_type: str) -> None:
    role = STAGE_ROLE_BY_TYPE.get(stage_type)
    if not role:
        frappe.throw(_("Unsupported shop-floor stage: {0}").format(stage_type))
    if not user:
        frappe.throw(_("Select a worker."))
    if not frappe.db.exists("User", user) or not cint(
        frappe.db.get_value("User", user, "enabled")
    ):
        frappe.throw(_("User {0} is not an enabled system user.").format(user))
    user_roles = set(frappe.get_roles(user))
    if role not in user_roles and "System Manager" not in user_roles:
        frappe.throw(_("User {0} does not have role {1}.").format(user, role))


def require_stage_assignee_or_admin(stage: Any) -> None:
    roles = set(frappe.get_roles())
    if roles.intersection(STAGE_ADMIN_ROLES):
        return
    expected_role = STAGE_ROLE_BY_TYPE.get(stage.stage_type)
    if expected_role:
        require_roles(expected_role)
    if stage.assigned_to and stage.assigned_to != frappe.session.user:
        frappe.throw(_("This stage is assigned to another worker."))


def get_users_for_stage(stage_type: str) -> list[dict[str, str]]:
    role = STAGE_ROLE_BY_TYPE.get(stage_type)
    if not role:
        return []
    return get_users_for_role(role)


def get_users_for_role(role: str) -> list[dict[str, str]]:
    rows = frappe.db.sql(
        """
        select u.name, u.full_name
          from `tabUser` u
          inner join `tabHas Role` hr on hr.parent = u.name
         where hr.role = %s
           and u.enabled = 1
           and u.user_type = 'System User'
           and u.name not in ('Guest', 'Administrator')
         order by u.full_name asc
        """,
        (role,),
        as_dict=True,
    )
    return [
        {"name": row.name, "full_name": row.full_name or row.name}
        for row in rows
    ]


__all__ = [
    "ADMIN_ROLES",
    "DISPATCH_ROLES",
    "STAGE_ADMIN_ROLES",
    "STAGE_ROLE_BY_TYPE",
    "assert_enabled_user_has_stage_role",
    "current_user",
    "get_users_for_role",
    "get_users_for_stage",
    "require_roles",
    "require_stage_assignee_or_admin",
]
