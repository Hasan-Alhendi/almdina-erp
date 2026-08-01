from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import frappe
from frappe import _
from frappe.utils import cint

from almdina_erp.almdina_erp.application.security.permission_matrix import (
    capability_catalog_payload,
    changed_capabilities,
    normalize_capability_state,
    permission_impact,
)
from almdina_erp.almdina_erp.application.security.permission_templates import (
    PERMISSION_TRANSFER_SCHEMA,
    PERMISSION_TRANSFER_VERSION,
    build_permission_export,
    parse_permission_export,
    permission_template_catalog,
    template_state,
)
from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe.authorization_gateway import (
    require_doctype_capability,
)
from almdina_erp.almdina_erp.infrastructure.frappe.permission_matrix_repository import (
    FrappePermissionMatrixRepository,
)


_repository = FrappePermissionMatrixRepository()
_MAX_TRANSFER_BYTES = 128 * 1024


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
        if len(values.encode("utf-8")) > _MAX_TRANSFER_BYTES:
            frappe.throw(_("Permission payload is too large."))
        parsed = frappe.parse_json(values)
    elif isinstance(values, Mapping):
        parsed = dict(values)
    else:
        parsed = None
    if not isinstance(parsed, dict):
        frappe.throw(_(error_message))
    return parsed


def _parse_capabilities(values: str | Mapping[str, Any] | None) -> dict[str, bool]:
    parsed = _parse_json_object(
        values,
        error_message="Permission values must be an object.",
    )
    try:
        return normalize_capability_state(parsed)
    except ValueError as error:
        frappe.throw(_(str(error)))
    raise AssertionError("frappe.throw must interrupt execution")


def _parse_transfer(values: str | Mapping[str, Any] | None) -> dict[str, Any]:
    parsed = _parse_json_object(
        values,
        error_message="Permission import must be a JSON object.",
    )
    try:
        return parse_permission_export(parsed)
    except ValueError as error:
        frappe.throw(_(str(error)))
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
    source: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    normalized = normalize_capability_state(after)
    changes = changed_capabilities(before, normalized)
    result: dict[str, Any] = {
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
            change["risk"] in {"sensitive", "critical"} for change in changes
        ),
    }
    if source:
        result["source"] = dict(source)
    return result


@frappe.whitelist()
def get_permission_console(role: str | None = None) -> dict[str, Any]:
    """Return the complete, least-privilege permission console payload."""

    _require_permission_management()
    roles = _repository.list_roles()
    selected_role = str(role or "").strip()
    selected = _role_payload(selected_role) if selected_role else None
    return {
        "catalog": capability_catalog_payload(),
        "templates": permission_template_catalog(),
        "transfer": {
            "schema": PERMISSION_TRANSFER_SCHEMA,
            "version": PERMISSION_TRANSFER_VERSION,
            "max_bytes": _MAX_TRANSFER_BYTES,
        },
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
        frappe.throw(_(str(error)))
    raise AssertionError("frappe.throw must interrupt execution")


@frappe.whitelist()
def preview_role_permissions(
    role: str,
    capabilities: str | Mapping[str, Any],
) -> dict[str, Any]:
    _require_permission_management()
    try:
        before = _repository.role_state(role)["capabilities"]
        after = _parse_capabilities(capabilities)
    except ValueError as error:
        frappe.throw(_(str(error)))
    return _preview_payload(role=role, before=before, after=after)


@frappe.whitelist()
def preview_permission_template(role: str, template_key: str) -> dict[str, Any]:
    """Preview an optional least-privilege template without persisting it."""

    _require_permission_management()
    try:
        before = _repository.role_state(role)["capabilities"]
        after = template_state(template_key)
    except ValueError as error:
        frappe.throw(_(str(error)))
    return _preview_payload(
        role=role,
        before=before,
        after=after,
        source={"kind": "template", "key": str(template_key)},
    )


@frappe.whitelist()
def export_role_permissions(role: str) -> dict[str, Any]:
    """Export one role matrix as a versioned, checksummed JSON document."""

    _require_permission_management()
    try:
        state = _repository.role_state(role)["capabilities"]
    except ValueError as error:
        frappe.throw(_(str(error)))
    document = build_permission_export(role=role, state=state)
    document.update(
        {
            "exported_at": frappe.utils.now(),
            "exported_by": str(frappe.session.user),
        }
    )
    return document


@frappe.whitelist()
def preview_permission_import(
    role: str,
    payload: str | Mapping[str, Any],
) -> dict[str, Any]:
    """Validate and preview an imported matrix; saving remains explicit."""

    _require_permission_management()
    try:
        before = _repository.role_state(role)["capabilities"]
        imported = _parse_transfer(payload)
    except ValueError as error:
        frappe.throw(_(str(error)))
    return _preview_payload(
        role=role,
        before=before,
        after=imported["capabilities"],
        source={
            "kind": "import",
            "role": imported["source_role"],
            "schema": imported["schema"],
            "version": imported["version"],
        },
    )


@frappe.whitelist()
def update_role_permissions(
    role: str,
    capabilities: str | Mapping[str, Any],
    confirm_self_lockout: int | str = 0,
) -> dict[str, Any]:
    _require_permission_management()
    try:
        before = _repository.role_state(role)["capabilities"]
        after = _parse_capabilities(capabilities)
    except ValueError as error:
        frappe.throw(_(str(error)))

    changes = changed_capabilities(before, after)
    if not changes:
        return {
            **_role_payload(role),
            "changed": False,
            "audit_name": None,
        }

    if _self_lockout_warning(role, before, after) and not cint(confirm_self_lockout):
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
        frappe.throw(_(str(error)))
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
def get_permission_audit(role: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
    _require_permission_management()
    try:
        return _repository.list_audit(role or None, limit=limit)
    except ValueError as error:
        frappe.throw(_(str(error)))
    raise AssertionError("frappe.throw must interrupt execution")


__all__ = [
    "export_role_permissions",
    "get_permission_audit",
    "get_permission_console",
    "get_role_permissions",
    "preview_permission_import",
    "preview_permission_template",
    "preview_role_permissions",
    "update_role_permissions",
]
