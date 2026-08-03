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


def assert_enabled_user_has_role(user: str, role: str) -> None:
    """Ensure an assignee is active and belongs to the configured route role."""

    resolved_user = str(user or "").strip()
    resolved_role = str(role or "").strip()
    if not resolved_user:
        frappe.throw(_("Select a worker."))
    if not resolved_role:
        frappe.throw(_("The production stage has no operational role."))
    if not frappe.db.exists("Role", resolved_role):
        frappe.throw(_("Operational role {0} does not exist.").format(resolved_role))
    if not frappe.db.exists("User", resolved_user) or not cint(
        frappe.db.get_value("User", resolved_user, "enabled")
    ):
        frappe.throw(_("User {0} is not an enabled system user.").format(resolved_user))
    user_roles = set(frappe.get_roles(resolved_user))
    if resolved_role not in user_roles and resolved_user != "Administrator":
        frappe.throw(
            _("User {0} is not assigned to operational role {1}.").format(
                resolved_user,
                resolved_role,
            )
        )


def assert_enabled_user_has_stage_role(user: str, stage_type: str) -> None:
    """Validate operational eligibility for an assignment.

    Business action authorization is resolved separately through configurable
    Permission Types. This mapping only answers whether a selected worker is a
    member of the operational department represented by the stage type.
    """

    role = STAGE_ROLE_BY_TYPE.get(stage_type)
    if not role:
        frappe.throw(_("Unsupported shop-floor stage: {0}").format(stage_type))
    assert_enabled_user_has_role(user, role)


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
    "assert_enabled_user_has_role",
    "assert_enabled_user_has_stage_role",
    "current_user",
    "get_users_for_role",
    "get_users_for_stage",
]
