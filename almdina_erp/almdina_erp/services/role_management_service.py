from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Callable, TypeVar

import frappe
from frappe import _

from almdina_erp.almdina_erp.application.security.role_administration import (
    RoleAdministration,
    RoleAdministrationError,
)
from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe.authorization_gateway import (
    require_doctype_capability,
)
from almdina_erp.almdina_erp.infrastructure.frappe.role_repository import (
    FrappeRoleRepository,
)


_repository = FrappeRoleRepository()
_administration = RoleAdministration(_repository)
T = TypeVar("T")


def _require_role_management() -> None:
    require_doctype_capability(
        Capability.MANAGE_PERMISSIONS,
        message=_("You do not have permission to manage Almdina roles."),
    )


def _payload(value: str | Mapping[str, Any] | None) -> dict[str, Any]:
    if isinstance(value, str):
        parsed = frappe.parse_json(value)
    elif isinstance(value, Mapping):
        parsed = dict(value)
    else:
        parsed = None
    if not isinstance(parsed, dict):
        frappe.throw(_("Role values must be a JSON object."), frappe.ValidationError)
    return parsed


def _bool_value(value: Any) -> bool:
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off", ""}:
            return False
        raise ValueError("Invalid boolean value.")
    return bool(value)


def _execute(call: Callable[[], T]) -> T:
    try:
        return call()
    except RoleAdministrationError as error:
        frappe.throw(_(str(error)), frappe.ValidationError)
    except ValueError as error:
        frappe.throw(_(str(error)), frappe.ValidationError)
    raise AssertionError("frappe.throw must interrupt execution")


def _actor() -> str:
    return str(frappe.session.user)


@frappe.whitelist()
def get_role_console(
    search: str = "",
    enabled: int | str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """List editable roles with permission, user and production references."""

    _require_role_management()
    try:
        enabled_filter = (
            None if enabled in (None, "", "all") else _bool_value(enabled)
        )
    except ValueError as error:
        frappe.throw(_(str(error)), frappe.ValidationError)
    return _execute(
        lambda: _administration.console(
            actor=_actor(),
            search=search,
            enabled=enabled_filter,
            limit=limit,
        )
    )


@frappe.whitelist()
def get_role_details(role: str) -> dict[str, Any]:
    _require_role_management()
    return _execute(
        lambda: _administration.get(actor=_actor(), role=role)
    )


@frappe.whitelist()
def create_factory_role(data: str | Mapping[str, Any]) -> dict[str, Any]:
    """Create an enabled Desk role with zero implicit permissions."""

    _require_role_management()
    values = _payload(data)
    return _execute(
        lambda: _administration.create(
            actor=_actor(),
            name=str(values.get("name") or ""),
            description=values.get("description"),
        )
    )


@frappe.whitelist()
def update_factory_role(
    role: str,
    data: str | Mapping[str, Any],
) -> dict[str, Any]:
    """Rename a role or update its private Almdina description."""

    _require_role_management()
    values = _payload(data)
    return _execute(
        lambda: _administration.update(
            actor=_actor(),
            role=role,
            name=(
                str(values.get("name") or "")
                if "name" in values
                else None
            ),
            description=(
                str(values.get("description") or "")
                if "description" in values
                else None
            ),
        )
    )


@frappe.whitelist()
def set_factory_role_enabled(
    role: str,
    enabled: int | bool | str,
) -> dict[str, Any]:
    _require_role_management()
    try:
        resolved = _bool_value(enabled)
    except ValueError as error:
        frappe.throw(_(str(error)), frappe.ValidationError)
    return _execute(
        lambda: _administration.set_enabled(
            actor=_actor(),
            role=role,
            enabled=resolved,
        )
    )


@frappe.whitelist()
def delete_factory_role(
    role: str,
    confirm_delete: int | bool | str = 0,
) -> dict[str, Any]:
    """Delete only an empty role after explicit confirmation and reference checks."""

    _require_role_management()
    try:
        confirmed = _bool_value(confirm_delete)
    except ValueError as error:
        frappe.throw(_(str(error)), frappe.ValidationError)
    if not confirmed:
        frappe.throw(
            _("Confirm role deletion explicitly to continue."),
            frappe.ValidationError,
        )
    return _execute(
        lambda: _administration.delete(actor=_actor(), role=role)
    )


@frappe.whitelist()
def get_factory_role_audit(role: str, limit: int = 30) -> dict[str, Any]:
    _require_role_management()
    return _execute(
        lambda: _administration.audit(
            actor=_actor(),
            role=role,
            limit=limit,
        )
    )


__all__ = [
    "create_factory_role",
    "delete_factory_role",
    "get_factory_role_audit",
    "get_role_console",
    "get_role_details",
    "set_factory_role_enabled",
    "update_factory_role",
]
