from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence

import frappe

from almdina_erp.almdina_erp.infrastructure.frappe.routing_role_codec import (
    decode_eligible_roles,
    eligible_roles_display,
    encode_eligible_roles,
)


_SUPPORTED_SNAPSHOT_DOCTYPES = frozenset(
    {
        "Production Routing Stage",
        "Production Stage",
    }
)


def _assert_supported_doctype(doctype: str) -> str:
    resolved = str(doctype or "").strip()
    if resolved not in _SUPPORTED_SNAPSHOT_DOCTYPES:
        raise ValueError(f"Unsupported role snapshot DocType: {resolved or '<empty>'}")
    return resolved


def _role_fields(doctype: str) -> tuple[bool, bool, bool]:
    resolved = _assert_supported_doctype(doctype)
    if not frappe.db.exists("DocType", resolved):
        return False, False, False
    meta = frappe.get_meta(resolved)
    return (
        meta.has_field("eligible_roles_json"),
        meta.has_field("operational_role"),
        meta.has_field("eligible_roles_display"),
    )


def _decode_row_roles(
    row: Mapping[str, object],
    *,
    has_json: bool,
    has_legacy: bool,
) -> tuple[str, ...]:
    legacy = str(row.get("operational_role") or "").strip() if has_legacy else ""
    if not has_json:
        return (legacy,) if legacy else ()
    try:
        return decode_eligible_roles(
            row.get("eligible_roles_json"),
            legacy_role=legacy or None,
        )
    except ValueError:
        # A malformed historical JSON snapshot must still preserve the valid
        # Link fallback so referenced roles cannot be deleted or orphaned.
        return (legacy,) if legacy else ()


def configured_role_counts(
    doctype: str,
    roles: Sequence[str],
    *,
    filters: Mapping[str, object] | None = None,
) -> dict[str, int]:
    """Count records that reference each role in a persisted role-set snapshot.

    New schemas store all eligible roles in JSON. Older schemas may contain only
    ``operational_role``; that field remains a safe fallback during upgrades.
    One record counts at most once for a given role.
    """

    resolved_doctype = _assert_supported_doctype(doctype)
    if not roles:
        return {}
    has_json, has_legacy, _has_display = _role_fields(resolved_doctype)
    if not has_json and not has_legacy:
        return {}

    fields: list[str] = []
    if has_json:
        fields.append("eligible_roles_json")
    if has_legacy:
        fields.append("operational_role")
    rows = frappe.get_all(
        resolved_doctype,
        filters=dict(filters or {}),
        fields=fields,
        limit_page_length=0,
    )
    requested = {str(role).strip() for role in roles if str(role).strip()}
    counts: defaultdict[str, int] = defaultdict(int)
    for row in rows:
        configured = set(
            _decode_row_roles(
                row,
                has_json=has_json,
                has_legacy=has_legacy,
            )
        )
        for role in requested.intersection(configured):
            counts[role] += 1
    return dict(counts)


def _lock_snapshot_rows(doctype: str, names: Sequence[str]) -> None:
    resolved_names = tuple(sorted({str(name) for name in names if str(name)}))
    if not resolved_names:
        return
    placeholders = ", ".join(["%s"] * len(resolved_names))
    # The table identifier is safe because doctype passed through a strict
    # allowlist. Lock ordering is deterministic to avoid deadlocks.
    frappe.db.sql(
        f"select name from `tab{doctype}` "
        f"where name in ({placeholders}) order by name for update",
        resolved_names,
    )


def rename_configured_role_references(
    doctype: str,
    old_role: str,
    new_role: str,
) -> int:
    """Rename one role inside JSON snapshots and their compatibility fields."""

    resolved_doctype = _assert_supported_doctype(doctype)
    old_name = str(old_role or "").strip()
    new_name = str(new_role or "").strip()
    if not old_name or not new_name or old_name == new_name:
        return 0

    has_json, has_legacy, has_display = _role_fields(resolved_doctype)
    if not has_json and not has_legacy:
        return 0

    fields = ["name"]
    if has_json:
        fields.append("eligible_roles_json")
    if has_legacy:
        fields.append("operational_role")
    snapshot_rows = frappe.get_all(
        resolved_doctype,
        fields=fields,
        limit_page_length=0,
    )
    candidate_names = [
        str(row.get("name") or "")
        for row in snapshot_rows
        if old_name
        in _decode_row_roles(
            row,
            has_json=has_json,
            has_legacy=has_legacy,
        )
    ]
    if not candidate_names:
        return 0

    _lock_snapshot_rows(resolved_doctype, candidate_names)
    # Re-read after acquiring locks so a concurrent route save cannot leave a
    # stale snapshot between discovery and update.
    rows = frappe.get_all(
        resolved_doctype,
        filters={"name": ["in", candidate_names]},
        fields=fields,
        order_by="name asc",
        limit_page_length=0,
    )

    changed = 0
    for row in rows:
        roles = _decode_row_roles(
            row,
            has_json=has_json,
            has_legacy=has_legacy,
        )
        if old_name not in roles:
            continue

        renamed_roles = tuple(
            dict.fromkeys(new_name if role == old_name else role for role in roles)
        )
        values: dict[str, object] = {}
        if has_json:
            values["eligible_roles_json"] = encode_eligible_roles(renamed_roles)
        if has_display:
            values["eligible_roles_display"] = eligible_roles_display(renamed_roles)
        if has_legacy:
            values["operational_role"] = renamed_roles[0] if renamed_roles else None
        frappe.db.set_value(
            resolved_doctype,
            str(row.get("name") or ""),
            values,
            update_modified=False,
        )
        changed += 1
    return changed


__all__ = [
    "configured_role_counts",
    "rename_configured_role_references",
]
