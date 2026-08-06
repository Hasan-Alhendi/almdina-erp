from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence

import frappe

from almdina_erp.almdina_erp.infrastructure.frappe.routing_role_codec import (
    decode_eligible_roles,
    eligible_roles_display,
    encode_eligible_roles,
)


def _role_fields(doctype: str) -> tuple[bool, bool]:
    if not frappe.db.exists("DocType", doctype):
        return False, False
    meta = frappe.get_meta(doctype)
    return meta.has_field("eligible_roles_json"), meta.has_field("operational_role")


def configured_role_counts(
    doctype: str,
    roles: Sequence[str],
    *,
    filters: Mapping[str, object] | None = None,
) -> dict[str, int]:
    """Count records that reference each role in a persisted role-set snapshot."""

    if not roles:
        return {}
    has_json, has_legacy = _role_fields(doctype)
    if not has_json and not has_legacy:
        return {}

    fields: list[str] = []
    if has_json:
        fields.append("eligible_roles_json")
    if has_legacy:
        fields.append("operational_role")
    rows = frappe.get_all(
        doctype,
        filters=dict(filters or {}),
        fields=fields,
        limit_page_length=0,
    )
    requested = set(str(role) for role in roles)
    counts: defaultdict[str, int] = defaultdict(int)
    for row in rows:
        if has_json:
            try:
                configured = set(
                    decode_eligible_roles(
                        row.get("eligible_roles_json"),
                        legacy_role=(row.get("operational_role") if has_legacy else None),
                    )
                )
            except ValueError:
                legacy = (
                    str(row.get("operational_role") or "").strip()
                    if has_legacy
                    else ""
                )
                configured = {legacy} if legacy else set()
        else:
            legacy = str(row.get("operational_role") or "").strip()
            configured = {legacy} if legacy else set()
        for role in requested.intersection(configured):
            counts[role] += 1
    return dict(counts)


def rename_configured_role_references(
    doctype: str,
    old_role: str,
    new_role: str,
) -> int:
    """Rename one role inside every configured role-set snapshot."""

    old_name = str(old_role or "").strip()
    new_name = str(new_role or "").strip()
    if not old_name or not new_name or old_name == new_name:
        return 0
    has_json, has_legacy = _role_fields(doctype)
    if not has_json and not has_legacy:
        return 0

    fields = ["name"]
    if has_json:
        fields.append("eligible_roles_json")
    if has_legacy:
        fields.append("operational_role")
    rows = frappe.get_all(doctype, fields=fields, limit_page_length=0)
    changed = 0
    for row in rows:
        try:
            roles = list(
                decode_eligible_roles(
                    row.get("eligible_roles_json") if has_json else None,
                    legacy_role=(row.get("operational_role") if has_legacy else None),
                )
            )
        except ValueError:
            roles = []
        if old_name not in roles:
            continue
        renamed = tuple(new_name if role == old_name else role for role in roles)
        values: dict[str, object] = {}
        if has_json:
            values["eligible_roles_json"] = encode_eligible_roles(renamed)
        if frappe.get_meta(doctype).has_field("eligible_roles_display"):
            values["eligible_roles_display"] = eligible_roles_display(renamed)
        if has_legacy:
            values["operational_role"] = renamed[0] if renamed else ""
        frappe.db.set_value(
            doctype,
            row.name,
            values,
            update_modified=False,
        )
        changed += 1
    return changed


__all__ = [
    "configured_role_counts",
    "rename_configured_role_references",
]
