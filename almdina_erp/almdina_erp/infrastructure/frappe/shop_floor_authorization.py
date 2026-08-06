from __future__ import annotations

from collections.abc import Iterable

import frappe
from frappe import _
from frappe.utils import cint

from almdina_erp.almdina_erp.domain.orders.production_routing import (
    normalize_eligible_roles,
)
from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe.authorization_gateway import (
    granted_capabilities,
)


WORKER_EXECUTION_CAPABILITIES = frozenset(
    {
        Capability.START_ASSIGNED_STAGE,
        Capability.HANDOFF_ASSIGNED_STAGE,
    }
)
# Kept as an empty compatibility symbol. Stage eligibility is route data now.
STAGE_ROLE_BY_TYPE: dict[str, str] = {}


def current_user() -> str:
    return str(frappe.session.user)


def _enabled_system_user(user: str) -> bool:
    values = frappe.db.get_value(
        "User",
        user,
        ["enabled", "user_type"],
        as_dict=True,
    )
    return bool(
        values
        and cint(values.enabled)
        and str(values.user_type or "") == "System User"
    )


def assert_enabled_user_has_any_role(
    user: str,
    roles: Iterable[str] | str,
    *,
    required_capabilities: Iterable[str] = WORKER_EXECUTION_CAPABILITIES,
) -> None:
    """Ensure an assignee is active, role-eligible, and able to do the work."""

    resolved_user = str(user or "").strip()
    eligible_roles = normalize_eligible_roles(roles)
    if not resolved_user:
        frappe.throw(_("Select a worker."))
    if not eligible_roles:
        frappe.throw(_("The production stage has no eligible roles."))
    if not _enabled_system_user(resolved_user):
        frappe.throw(_("User {0} is not an enabled system user.").format(resolved_user))

    if resolved_user != "Administrator":
        user_roles = set(frappe.get_roles(resolved_user))
        if not user_roles.intersection(eligible_roles):
            frappe.throw(
                _("User {0} does not have an eligible role for this stage.").format(
                    resolved_user
                )
            )
        missing = set(required_capabilities).difference(
            granted_capabilities(resolved_user)
        )
        if missing:
            frappe.throw(
                _(
                    "User {0} has an eligible role but is missing the stage execution permissions."
                ).format(resolved_user)
            )


def assert_enabled_user_has_role(user: str, role: str) -> None:
    """Compatibility wrapper for callers that still pass one configured role."""

    assert_enabled_user_has_any_role(user, (role,))


def assert_enabled_user_has_stage_role(user: str, stage_type: str) -> None:
    """Fail closed: a stage code alone no longer determines eligibility."""

    del user
    frappe.throw(
        _(
            "Stage {0} has no role policy by code. Read eligible roles from its production route."
        ).format(stage_type),
        frappe.ValidationError,
    )


def get_users_for_stage(stage_type: str) -> list[dict[str, str]]:
    """Compatibility endpoint cannot infer roles from a stage code anymore."""

    del stage_type
    return []


def get_users_for_roles(
    roles: Iterable[str] | str,
    *,
    required_capabilities: Iterable[str] = WORKER_EXECUTION_CAPABILITIES,
) -> list[dict[str, str]]:
    eligible_roles = normalize_eligible_roles(roles)
    if not eligible_roles:
        return []
    placeholders = ", ".join(["%s"] * len(eligible_roles))
    rows = frappe.db.sql(
        f"""
        select distinct u.name, u.full_name
          from `tabUser` u
          inner join `tabHas Role` hr on hr.parent = u.name
         where hr.role in ({placeholders})
           and u.enabled = 1
           and u.user_type = 'System User'
           and u.name not in ('Guest', 'Administrator')
         order by u.full_name asc
        """,
        eligible_roles,
        as_dict=True,
    )
    required = frozenset(required_capabilities)
    result: list[dict[str, str]] = []
    for row in rows:
        capabilities = granted_capabilities(str(row.name))
        if required.difference(capabilities):
            continue
        user_roles = sorted(set(frappe.get_roles(str(row.name))).intersection(eligible_roles))
        result.append(
            {
                "name": str(row.name),
                "full_name": str(row.full_name or row.name),
                "eligible_roles": user_roles,
            }
        )
    return result


def get_users_for_role(role: str) -> list[dict[str, str]]:
    return get_users_for_roles((role,))


__all__ = [
    "STAGE_ROLE_BY_TYPE",
    "WORKER_EXECUTION_CAPABILITIES",
    "assert_enabled_user_has_any_role",
    "assert_enabled_user_has_role",
    "assert_enabled_user_has_stage_role",
    "current_user",
    "get_users_for_role",
    "get_users_for_roles",
    "get_users_for_stage",
]
