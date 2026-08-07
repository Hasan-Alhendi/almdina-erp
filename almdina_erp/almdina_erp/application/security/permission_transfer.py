from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any

from almdina_erp.almdina_erp.application.security.permission_matrix import (
    changed_capabilities,
    normalize_capability_state,
    permission_impact,
)


PERMISSION_TRANSFER_SCHEMA = "almdina.permission-matrix"
PERMISSION_TRANSFER_VERSION = 1
MAX_TRANSFER_ROLES = 500


def _enabled_capabilities(state: Mapping[str, Any] | None) -> list[str]:
    normalized = normalize_capability_state(state)
    return sorted(
        capability
        for capability, granted in normalized.items()
        if granted is True
    )


def _checksum(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        dict(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _canonical_transfer_payload(
    *,
    role: str,
    capabilities: Sequence[str],
) -> dict[str, Any]:
    return {
        "schema": PERMISSION_TRANSFER_SCHEMA,
        "version": PERMISSION_TRANSFER_VERSION,
        "role": str(role or "").strip(),
        "capabilities": sorted(str(value) for value in capabilities),
    }


def build_permission_export(
    *,
    role: str,
    state: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Build a stable checksummed single-role permission document."""

    canonical = _canonical_transfer_payload(
        role=role,
        capabilities=_enabled_capabilities(state),
    )
    return {**canonical, "checksum": _checksum(canonical)}


def parse_permission_export(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    document = dict(payload or {})
    if document.get("schema") != PERMISSION_TRANSFER_SCHEMA:
        raise ValueError("Unsupported permission export schema.")
    if document.get("version") != PERMISSION_TRANSFER_VERSION:
        raise ValueError("Unsupported permission export version.")

    source_role = str(document.get("role") or "").strip()
    if not source_role:
        raise ValueError("Permission export role is required.")
    capabilities = document.get("capabilities")
    if isinstance(capabilities, (str, bytes)) or not isinstance(
        capabilities, Sequence
    ):
        raise ValueError("Permission export capabilities must be a list.")
    if any(
        not isinstance(value, str) or not value.strip()
        for value in capabilities
    ):
        raise ValueError("Permission export contains an invalid capability key.")

    canonical = _canonical_transfer_payload(
        role=source_role,
        capabilities=list(capabilities),
    )
    checksum = str(document.get("checksum") or "").strip()
    if not checksum or checksum != _checksum(canonical):
        raise ValueError("Permission export checksum is invalid.")

    state = normalize_capability_state(
        {capability: True for capability in canonical["capabilities"]}
    )
    return {
        "source_role": source_role,
        "schema": PERMISSION_TRANSFER_SCHEMA,
        "version": PERMISSION_TRANSFER_VERSION,
        "capabilities": state,
    }


def _canonical_bundle_roles(
    role_states: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    roles: list[dict[str, Any]] = []
    for raw_role, state in sorted(role_states.items()):
        role = str(raw_role or "").strip()
        if not role:
            raise ValueError("Permission bundle roles must have a name.")
        roles.append(
            {
                "role": role,
                "capabilities": _enabled_capabilities(state),
            }
        )
    if not roles:
        raise ValueError("Permission bundle must contain at least one role.")
    if len(roles) > MAX_TRANSFER_ROLES:
        raise ValueError(
            f"Permission bundle cannot contain more than {MAX_TRANSFER_ROLES} roles."
        )
    return roles


def _canonical_bundle_payload(
    role_states: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    return {
        "schema": PERMISSION_TRANSFER_SCHEMA,
        "version": PERMISSION_TRANSFER_VERSION,
        "kind": "role_matrix",
        "roles": _canonical_bundle_roles(role_states),
    }


def build_permission_bundle(
    role_states: Mapping[str, Mapping[str, Any]],
    *,
    exported_by: str,
    exported_at: str,
    app_version: str,
) -> dict[str, Any]:
    """Build a checksummed multi-role bundle without users or audit records."""

    canonical = _canonical_bundle_payload(role_states)
    return {
        **canonical,
        "app_version": str(app_version or ""),
        "exported_by": str(exported_by or ""),
        "exported_at": str(exported_at or ""),
        "checksum": _checksum(canonical),
    }


def parse_permission_bundle(
    payload: Mapping[str, Any] | None,
) -> dict[str, dict[str, bool]]:
    document = dict(payload or {})
    if document.get("schema") != PERMISSION_TRANSFER_SCHEMA:
        raise ValueError("Unsupported permission bundle schema.")
    if document.get("version") != PERMISSION_TRANSFER_VERSION:
        raise ValueError("Unsupported permission bundle version.")
    if document.get("kind") != "role_matrix":
        raise ValueError("Permission bundle kind must be role_matrix.")

    raw_roles = document.get("roles")
    if not isinstance(raw_roles, list) or not raw_roles:
        raise ValueError("Permission bundle must contain a non-empty roles list.")
    if len(raw_roles) > MAX_TRANSFER_ROLES:
        raise ValueError(
            f"Permission bundle cannot contain more than {MAX_TRANSFER_ROLES} roles."
        )

    role_states: dict[str, dict[str, bool]] = {}
    for row in raw_roles:
        if not isinstance(row, dict):
            raise ValueError("Every permission bundle role must be an object.")
        role = str(row.get("role") or "").strip()
        if not role:
            raise ValueError("Permission bundle roles must have a name.")
        if role in role_states:
            raise ValueError(f"Permission bundle contains duplicate role: {role}")
        capabilities = row.get("capabilities")
        if isinstance(capabilities, (str, bytes)) or not isinstance(
            capabilities, Sequence
        ):
            raise ValueError(
                f"Permission bundle role {role} must contain a capabilities list."
            )
        if any(
            not isinstance(value, str) or not value.strip()
            for value in capabilities
        ):
            raise ValueError(
                f"Permission bundle role {role} contains an invalid capability key."
            )
        role_states[role] = normalize_capability_state(
            {capability: True for capability in capabilities}
        )

    canonical = _canonical_bundle_payload(role_states)
    checksum = str(document.get("checksum") or "").strip()
    if not checksum or checksum != _checksum(canonical):
        raise ValueError("Permission bundle checksum is invalid.")
    return role_states


def preview_permission_bundle(
    current_states: Mapping[str, Mapping[str, Any]],
    imported_states: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    role_previews: list[dict[str, Any]] = []
    for role in sorted(imported_states):
        before = normalize_capability_state(current_states.get(role))
        after = normalize_capability_state(imported_states[role])
        changes = changed_capabilities(before, after)
        role_previews.append(
            {
                "role": role,
                "changed": bool(changes),
                "changes": changes,
                "capabilities": after,
                "impact": permission_impact(after),
            }
        )

    all_changes = [
        change
        for row in role_previews
        for change in row["changes"]
    ]
    return {
        "roles": role_previews,
        "summary": {
            "role_count": len(role_previews),
            "changed_role_count": sum(
                1 for row in role_previews if row["changed"]
            ),
            "change_count": len(all_changes),
            "critical_change_count": sum(
                1 for change in all_changes if change["risk"] == "critical"
            ),
        },
    }


__all__ = [
    "MAX_TRANSFER_ROLES",
    "PERMISSION_TRANSFER_SCHEMA",
    "PERMISSION_TRANSFER_VERSION",
    "build_permission_bundle",
    "build_permission_export",
    "parse_permission_bundle",
    "parse_permission_export",
    "preview_permission_bundle",
]
