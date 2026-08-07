from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import frappe
from frappe import _
from frappe.utils import cint

from almdina_erp.almdina_erp.application.security.permission_matrix import (
    capability_catalog_payload,
    changed_capabilities,
    permission_impact,
    validate_capability_dependencies,
)
from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe.authorization_gateway import (
    require_doctype_capability,
)
from almdina_erp.almdina_erp.infrastructure.frappe.permission_matrix_repository import (
    FrappePermissionMatrixRepository,
)


_repository = FrappePermissionMatrixRepository()
_MAX_PERMISSION_PAYLOAD_BYTES = 64 * 1024


def _require_permission_management() -> None:
    require_doctype_capability(
        Capability.MANAGE_PERMISSIONS,
        message=_("You do not have permission to manage Almdina permissions."),
    )


def _parse_json_object(
    values: str | Mapping[str, Any] | None,
    *,
    error_message: str,
) -> dict[str, Any]:
    if isinstance(values, str):
        if len(values.encode("utf-8")) > _MAX_PERMISSION_PAYLOAD_BYTES:
            frappe.throw(_("Permission payload is too large."), frappe.ValidationError)
        parsed = frappe.parse_json(values)
    elif isinstance(values, Mapping):
        parsed = dict(values)
    else:
        parsed = None
    if not isinstance(parsed, dict):
        frappe.throw(_(error_message), frappe.ValidationError)
    return parsed


def _parse_capabilities(
    values: str | Mapping[str, Any] | None,
) -> dict[str, bool]:
    parsed = _parse_json_object(
        values,
        error_message="Permission values must be an object.",
    )
    try:
        return validate_capability_dependencies(parsed)
    except ValueError as error:
        frappe.throw(_(str(error)), frappe.ValidationError)
    raise AssertionError("frappe.throw must interrupt execution")


def _self_lockout_warning(
    role: str,
    before: Mapping[str, Any],
    after: Mapping[str, Any],
) -> bool:
    actor = str(frappe.session.user)
    if actor == "Administrator":
        return False
    if role not in _repository.user_roles(actor):
        return False
    if before.get(Capability.MANAGE_PERMISSIONS) is not True:
        return False
    if after.get(Capability.MANAGE_PERMISSIONS) is True:
        return False
    return not _repository.user_has_capability_outside_role(
        user=actor,
        excluded_role=role,
        capability=Capability.MANAGE_PERMISSIONS,
    )


def _role_payload(role: str) -> dict[str, Any]:
    state = _repository.role_state(role)
    capabilities = state["capabilities"]
    return {
        **state,
        "impact": permission_impact(capabilities),
        "audit": _repository.list_audit(role, limit=20),
    }


def _preview_payload(
    *,
    role: str,
    before: Mapping[str, Any],
    after: Mapping[str, Any],
) -> dict[str, Any]:
    try:
        normalized = validate_capability_dependencies(after)
    except ValueError as error:
        frappe.throw(_(str(error)), frappe.ValidationError)
    changes = changed_capabilities(before, normalized)
    return {
        "role": role,
        "capabilities": normalized,
        "changes": changes,
        "impact": permission_impact(normalized),
        "requires_self_lockout_confirmation": _self_lockout_warning(
            role,
            before,
            normalized,
        ),
        "has_sensitive_changes": any(
            change["risk"] in {"sensitive", "critical"}
            for change in changes
        ),
    }


@frappe.whitelist()
def get_permission_console(role: str | None = None) -> dict[str, Any]:
    """Return the manual permission console payload for Almdina-managed roles."""

    _require_permission_management()
    roles = _repository.list_roles()
    selected_role = str(role or "").strip()
    try:
        selected = _role_payload(selected_role) if selected_role else None
    except ValueError as error:
        frappe.throw(_(str(error)), frappe.ValidationError)
    return {
        "catalog": capability_catalog_payload(),
        "roles": roles,
        "selected": selected,
        "actor": {
            "user": frappe.session.user,
            "full_name": frappe.utils.get_fullname(frappe.session.user),
        },
    }


@frappe.whitelist()
def get_role_permissions(role: str) -> dict[str, Any]:
    _require_permission_management()
    try:
        return _role_payload(role)
    except ValueError as error:
        frappe.throw(_(str(error)), frappe.ValidationError)
    raise AssertionError("frappe.throw must interrupt execution")


@frappe.whitelist()
def preview_role_permissions(
    role: str,
    capabilities: str | Mapping[str, Any],
) -> dict[str, Any]:
    _require_permission_management()
    try:
        before = _repository.role_state(role)["capabilities"]
    except ValueError as error:
        frappe.throw(_(str(error)), frappe.ValidationError)
    after = _parse_capabilities(capabilities)
    return _preview_payload(role=role, before=before, after=after)


@frappe.whitelist()
def update_role_permissions(
    role: str,
    capabilities: str | Mapping[str, Any],
    confirm_self_lockout: int | str = 0,
) -> dict[str, Any]:
    _require_permission_management()
    try:
        before = _repository.role_state(role)["capabilities"]
    except ValueError as error:
        frappe.throw(_(str(error)), frappe.ValidationError)
    after = _parse_capabilities(capabilities)

    changes = changed_capabilities(before, after)
    if not changes:
        try:
            _repository.save_role_state(role, after)
        except ValueError as error:
            frappe.throw(_(str(error)), frappe.ValidationError)
        return {
            **_role_payload(role),
            "changed": False,
            "audit_name": None,
        }

    if _self_lockout_warning(role, before, after) and not cint(
        confirm_self_lockout
    ):
        frappe.throw(
            _(
                "This change removes your last permission-management grant. "
                "Confirm the self-lockout explicitly to continue."
            ),
            frappe.PermissionError,
        )

    try:
        saved = _repository.save_role_state(role, after)
    except ValueError as error:
        frappe.throw(_(str(error)), frappe.ValidationError)
    audit_name = _repository.record_audit(
        role=role,
        before=before,
        after=saved["capabilities"],
        changed_by=str(frappe.session.user),
    )
    return {
        **_role_payload(role),
        "changed": True,
        "audit_name": audit_name,
        "changes": changes,
    }


@frappe.whitelist()
def get_permission_audit(
    role: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    _require_permission_management()
    try:
        return _repository.list_audit(role or None, limit=limit)
    except ValueError as error:
        frappe.throw(_(str(error)), frappe.ValidationError)
    raise AssertionError("frappe.throw must interrupt execution")


__all__ = [
    "get_permission_audit",
    "get_permission_console",
    "get_role_permissions",
    "preview_role_permissions",
    "update_role_permissions",
]
