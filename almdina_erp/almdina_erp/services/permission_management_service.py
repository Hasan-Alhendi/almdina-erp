from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import frappe
from frappe import _
from frappe.utils import cint

from almdina_erp import __version__
from almdina_erp.almdina_erp.application.security.permission_matrix import (
    capability_catalog_payload,
    changed_capabilities,
    normalize_capability_state,
    permission_impact,
)
from almdina_erp.almdina_erp.application.security.permission_transfer import (
    PERMISSION_TRANSFER_SCHEMA,
    PERMISSION_TRANSFER_VERSION,
    build_permission_bundle,
    build_permission_export,
    parse_permission_bundle,
    parse_permission_export,
    preview_permission_bundle,
)
from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe.authorization_gateway import (
    require_doctype_capability,
)
from almdina_erp.almdina_erp.infrastructure.frappe.permission_matrix_repository import (
    FrappePermissionMatrixRepository,
    PROTECTED_ROLES,
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


def _parse_capabilities(
    values: str | Mapping[str, Any] | None,
) -> dict[str, bool]:
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


def _parse_bundle(
    values: str | Mapping[str, Any] | None,
) -> dict[str, dict[str, bool]]:
    parsed = _parse_json_object(
        values,
        error_message="Permission bundle must be a JSON object.",
    )
    try:
        return parse_permission_bundle(parsed)
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


def _bulk_self_lockout_warning(
    imported_states: Mapping[str, Mapping[str, Any]],
) -> bool:
    actor = str(frappe.session.user)
    if actor == "Administrator":
        return False

    current_states: dict[str, dict[str, bool]] = {}
    for role in _repository.user_roles(actor):
        if role in PROTECTED_ROLES:
            continue
        try:
            current_states[role] = _repository.role_state(role)["capabilities"]
        except ValueError:
            continue
    if not any(
        state.get(Capability.MANAGE_PERMISSIONS) is True
        for state in current_states.values()
    ):
        return False

    for role, current in current_states.items():
        effective = imported_states.get(role, current)
        if normalize_capability_state(effective).get(
            Capability.MANAGE_PERMISSIONS
        ) is True:
            return False
    return True


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
            change["risk"] in {"sensitive", "critical"}
            for change in changes
        ),
    }
    if source:
        result["source"] = dict(source)
    return result


def _bundle_preview(
    payload: str | Mapping[str, Any],
) -> tuple[dict[str, dict[str, bool]], dict[str, Any]]:
    imported = _parse_bundle(payload)
    try:
        current = _repository.role_states(list(imported))
    except ValueError as error:
        frappe.throw(_(str(error)))
    preview = preview_permission_bundle(current, imported)
    preview.update(
        {
            "schema": PERMISSION_TRANSFER_SCHEMA,
            "version": PERMISSION_TRANSFER_VERSION,
            "requires_self_lockout_confirmation": (
                _bulk_self_lockout_warning(imported)
            ),
            "has_sensitive_changes": any(
                change["risk"] in {"sensitive", "critical"}
                for row in preview["roles"]
                for change in row["changes"]
            ),
        }
    )
    return imported, preview


@frappe.whitelist()
def get_permission_console(role: str | None = None) -> dict[str, Any]:
    """Return the permission catalog, roles and secure transfer metadata."""

    _require_permission_management()
    roles = _repository.list_roles()
    selected_role = str(role or "").strip()
    selected = _role_payload(selected_role) if selected_role else None
    return {
        "catalog": capability_catalog_payload(),
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
def export_permission_bundle(role: str | None = None) -> dict[str, Any]:
    """Export one or all role matrices without users, passwords, or audit data."""

    _require_permission_management()
    selected = str(role or "").strip()
    try:
        states = _repository.role_states([selected] if selected else None)
        return build_permission_bundle(
            states,
            exported_by=str(frappe.session.user),
            exported_at=str(frappe.utils.now()),
            app_version=__version__,
        )
    except ValueError as error:
        frappe.throw(_(str(error)))
    raise AssertionError("frappe.throw must interrupt execution")


@frappe.whitelist()
def preview_permission_import(
    role: str,
    payload: str | Mapping[str, Any],
) -> dict[str, Any]:
    """Validate and preview a single-role import; saving remains explicit."""

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
def preview_permission_bundle_import(
    payload: str | Mapping[str, Any],
) -> dict[str, Any]:
    """Validate all target roles and preview a matrix import without writes."""

    _require_permission_management()
    _, preview = _bundle_preview(payload)
    return preview


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
        # A no-op console save is also a safe repair operation. Older releases
        # could persist capability columns without their native create/write or
        # higher field-level projection, leaving the switches enabled while the
        # form stayed read-only or empty.
        try:
            _repository.save_role_state(role, after)
        except ValueError as error:
            frappe.throw(_(str(error)))
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
def import_permission_bundle(
    payload: str | Mapping[str, Any],
    confirm_sensitive: int | str = 0,
    confirm_self_lockout: int | str = 0,
) -> dict[str, Any]:
    """Atomically import a complete matrix into existing roles only."""

    _require_permission_management()
    imported, preview = _bundle_preview(payload)
    if not preview["summary"]["change_count"]:
        return {**preview, "changed": False, "audit_names": []}
    if preview["has_sensitive_changes"] and not cint(confirm_sensitive):
        frappe.throw(
            _(
                "This import contains sensitive or critical permission changes. "
                "Confirm them explicitly to continue."
            ),
            frappe.PermissionError,
        )
    if preview["requires_self_lockout_confirmation"] and not cint(
        confirm_self_lockout
    ):
        frappe.throw(
            _(
                "This import removes your last permission-management grant. "
                "Confirm the self-lockout explicitly to continue."
            ),
            frappe.PermissionError,
        )

    before_states = _repository.role_states(list(imported))
    try:
        saved = _repository.save_role_states(imported)
    except ValueError as error:
        frappe.throw(_(str(error)))

    audit_names: list[str] = []
    for role in sorted(imported):
        audit_name = _repository.record_audit(
            role=role,
            before=before_states[role],
            after=saved[role]["capabilities"],
            changed_by=str(frappe.session.user),
            source="Almdina Permission Import",
        )
        if audit_name:
            audit_names.append(audit_name)
    final_states = {
        role: saved[role]["capabilities"] for role in sorted(saved)
    }
    result = preview_permission_bundle(before_states, final_states)
    return {
        **result,
        "changed": True,
        "audit_names": audit_names,
        "has_sensitive_changes": preview["has_sensitive_changes"],
        "requires_self_lockout_confirmation": preview[
            "requires_self_lockout_confirmation"
        ],
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
        frappe.throw(_(str(error)))
    raise AssertionError("frappe.throw must interrupt execution")


__all__ = [
    "export_permission_bundle",
    "export_role_permissions",
    "get_permission_audit",
    "get_permission_console",
    "get_role_permissions",
    "import_permission_bundle",
    "preview_permission_bundle_import",
    "preview_permission_import",
    "preview_role_permissions",
    "update_role_permissions",
]
