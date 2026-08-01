from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

import frappe


_IGNORED_FIELDS = frozenset(
    {
        "doctype",
        "name",
        "owner",
        "creation",
        "modified",
        "modified_by",
        "docstatus",
        "idx",
        "parent",
        "parentfield",
        "parenttype",
        "_user_tags",
        "_comments",
        "_assign",
        "_liked_by",
    }
)


def _skip_audit() -> bool:
    return any(
        bool(getattr(frappe.flags, flag, False))
        for flag in ("in_install", "in_migrate", "in_patch", "in_import")
    )


def _json_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if hasattr(value, "as_dict"):
        return _json_value(value.as_dict())
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def document_snapshot(document: Any | None) -> dict[str, Any]:
    if document is None:
        return {}
    values: dict[str, Any] = {}
    for field in document.meta.fields:
        fieldname = str(field.fieldname or "")
        if not fieldname or fieldname in _IGNORED_FIELDS:
            continue
        values[fieldname] = _json_value(document.get(fieldname))
    return values


def changed_fields(before: Mapping[str, Any], after: Mapping[str, Any]) -> list[str]:
    return sorted(
        key
        for key in set(before) | set(after)
        if before.get(key) != after.get(key)
    )


def record_master_data_audit(
    *,
    target_doctype: str,
    target_name: str,
    action: str,
    before: Mapping[str, Any] | None,
    after: Mapping[str, Any] | None,
    source: str,
    changed_by: str | None = None,
) -> str | None:
    if _skip_audit():
        return None
    before_state = dict(before or {})
    after_state = dict(after or {})
    fields = changed_fields(before_state, after_state)
    if action in {"Updated", "Settings Updated"} and not fields:
        return None
    document = frappe.get_doc(
        {
            "doctype": "Almdina Master Data Audit",
            "target_doctype": target_doctype,
            "target_name": target_name,
            "action": action,
            "changed_by": changed_by or frappe.session.user,
            "changed_on": frappe.utils.now(),
            "source": source,
            "changed_fields": ", ".join(fields),
            "before_json": json.dumps(before_state, ensure_ascii=False, sort_keys=True, default=str),
            "after_json": json.dumps(after_state, ensure_ascii=False, sort_keys=True, default=str),
        }
    ).insert(ignore_permissions=True)
    return str(document.name)


def audit_saved_document(document: Any, *, source: str = "Frappe Form") -> str | None:
    before_document = document.get_doc_before_save()
    before = document_snapshot(before_document)
    after = document_snapshot(document)
    action = "Created" if before_document is None else "Updated"
    return record_master_data_audit(
        target_doctype=str(document.doctype),
        target_name=str(document.name),
        action=action,
        before=before,
        after=after,
        source=source,
    )


def audit_deleted_document(document: Any, *, source: str = "Frappe Form") -> str | None:
    return record_master_data_audit(
        target_doctype=str(document.doctype),
        target_name=str(document.name),
        action="Deleted",
        before=document_snapshot(document),
        after={},
        source=source,
    )


__all__ = [
    "audit_deleted_document",
    "audit_saved_document",
    "changed_fields",
    "document_snapshot",
    "record_master_data_audit",
]
