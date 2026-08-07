from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint


def current_user() -> str:
    return str(frappe.session.user)


def assert_enabled_user_has_role(user: str, role: str) -> None:
    """Ensure an assignee is active and belongs to the route's configured role."""

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
           and u.name not in ('Guest', 'Administrator')
         order by u.full_name asc
        """,
        (resolved_role,),
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
