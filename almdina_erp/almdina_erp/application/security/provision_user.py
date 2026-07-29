from __future__ import annotations

from dataclasses import dataclass

import frappe
from frappe import _
from frappe.utils.password import update_password


@dataclass(frozen=True, slots=True)
class UserProfile:
    roles: tuple[str, ...]
    default_workspace: str
    default_app: str = "almdina_erp"


PROFILES: dict[str, UserProfile] = {
    "order_entry": UserProfile(("Order Entry",), "Almdina ERP"),
    "factory_manager": UserProfile(
        (
            "Order Entry",
            "Production Manager",
            "Accounts Management",
        ),
        "Almdina ERP",
    ),
    "production_manager": UserProfile(("Production Manager",), "Almdina ERP"),
    "accounts": UserProfile(("Accounts Management",), "Almdina ERP"),
    "drawing_operator": UserProfile(("عامل رسم",), "Shop Floor"),
    "sharyoun_operator": UserProfile(("عامل شريون",), "Shop Floor"),
    "cnc_operator": UserProfile(("عامل CNC",), "Shop Floor"),
    "sanding_operator": UserProfile(("عامل تقشيط",), "Shop Floor"),
}


def _require_system_manager() -> None:
    if "System Manager" not in set(frappe.get_roles()):
        frappe.throw(
            _("Only System Manager can provision Almdina ERP users."),
            frappe.PermissionError,
        )


def _validate_profile(profile: str) -> UserProfile:
    try:
        return PROFILES[profile]
    except KeyError:
        frappe.throw(
            _("Unknown Almdina user profile: {0}").format(profile),
        )
    raise AssertionError("frappe.throw must interrupt execution")


def _ensure_roles_exist(roles: tuple[str, ...]) -> None:
    missing = [role for role in roles if not frappe.db.exists("Role", role)]
    if missing:
        frappe.throw(
            _("Create the required roles before provisioning this user: {0}").format(
                ", ".join(missing)
            )
        )


def provision_user(
    email: str,
    profile: str,
    first_name: str,
    last_name: str = "",
    temporary_password: str | None = None,
    language: str = "ar",
) -> dict[str, object]:
    """Create or update one user from an explicit administrative command.

    Passwords are runtime inputs and are never stored in the repository. Existing
    users keep unrelated roles; this use case only adds roles required by the
    selected Almdina profile.
    """

    _require_system_manager()
    selected = _validate_profile(profile)
    _ensure_roles_exist(selected.roles)

    email = str(email or "").strip().lower()
    first_name = str(first_name or "").strip()
    if not email or "@" not in email:
        frappe.throw(_("A valid user email is required."))
    if not first_name:
        frappe.throw(_("First name is required."))
    if not temporary_password:
        frappe.throw(
            _("Pass a temporary password explicitly; no default password is stored in code.")
        )

    created = not frappe.db.exists("User", email)
    if created:
        user = frappe.get_doc(
            {
                "doctype": "User",
                "email": email,
                "first_name": first_name,
                "last_name": last_name or "",
                "send_welcome_email": 0,
                "user_type": "System User",
                "language": language or "ar",
                "enabled": 1,
            }
        )
        user.insert(ignore_permissions=True)
    else:
        user = frappe.get_doc("User", email)
        user.enabled = 1
        user.first_name = first_name
        user.last_name = last_name or ""
        user.language = language or "ar"

    current_roles = {row.role for row in (user.roles or [])}
    required_roles = ("Desk User", *selected.roles)
    added_roles: list[str] = []
    for role in required_roles:
        if role not in current_roles and frappe.db.exists("Role", role):
            user.append("roles", {"role": role})
            current_roles.add(role)
            added_roles.append(role)

    if frappe.db.exists("Workspace", selected.default_workspace):
        user.default_workspace = selected.default_workspace
    user.default_app = selected.default_app
    user.flags.ignore_permissions = True
    user.flags.ignore_password_policy = True
    user.save(ignore_permissions=True)
    update_password(email, temporary_password)

    return {
        "email": email,
        "profile": profile,
        "created": created,
        "roles_added": added_roles,
        "default_workspace": selected.default_workspace,
        "default_app": selected.default_app,
    }
