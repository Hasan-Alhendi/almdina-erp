from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence

import frappe

from almdina_erp.almdina_erp.infrastructure.frappe.routing_role_codec import (
    decode_eligible_roles,
)


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

    if not roles or not frappe.db.exists("DocType", doctype):
        return {}
    meta = frappe.get_meta(doctype)
    has_json = meta.has_field("eligible_roles_json")
    has_legacy = meta.has_field("operational_role")
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


__all__ = ["configured_role_counts"]
