from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint


STAGE_ROLE_BY_TYPE: dict[str, str] = {
    "Sharyoun": "عامل شريون",
    "Drawing": "عامل رسم",
    "CNC": "عامل CNC",
    "Sanding": "عامل تقشيط",
}


def current_user() -> str:
    return str(frappe.session.user)


def assert_enabled_user_has_stage_role(user: str, stage_type: str) -> None:
    """Validate operational eligibility for an assignment.

    Business action authorization is resolved separately through configurable
    Permission Types. This mapping only answers whether a selected worker is a
    member of the operational department represented by the stage type.
    """

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
    if role not in user_roles and user != "Administrator":
        frappe.throw(_("User {0} is not assigned to department {1}.").format(user, role))


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
    "STAGE_ROLE_BY_TYPE",
    "assert_enabled_user_has_stage_role",
    "current_user",
    "get_users_for_role",
    "get_users_for_stage",
]
