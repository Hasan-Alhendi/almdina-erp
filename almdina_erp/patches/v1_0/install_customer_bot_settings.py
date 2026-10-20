"""Install or extend customer-bot settings without replacing a saved copy.

The bot stays off. Repeated migrate repairs the permission column and adds only
missing catalog keys to an existing draft or published copy.
"""

from __future__ import annotations


def execute() -> None:
    import frappe

    from almdina_erp.almdina_erp.domain.customer_bot.message_defaults import default_texts
    from almdina_erp.almdina_erp.domain.customer_bot.message_templates import (
        dump_texts,
        load_texts,
    )
    from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_settings_records import (
        SERVICE_FLAG,
    )
    from almdina_erp.almdina_erp.infrastructure.frappe.permission_type_sync import (
        sync_permission_types,
    )

    sync_permission_types()
    # A Single has no table of its own. DocType existence is not a saved copy.
    existing = frappe.db.sql(
        "select 1 from `tabSingles` where doctype=%s and field='revision' limit 1",
        ("Customer Bot Settings",),
    )
    if existing:
        rows = frappe.db.sql(
            "select field, value from `tabSingles` where doctype=%s and field in ('revision', 'draft_texts', 'published_texts')",
            ("Customer Bot Settings",),
            as_dict=True,
        )
        values = {row.field: row.value for row in rows}
        defaults = default_texts()
        draft = _merge_texts(load_texts(values.get("draft_texts")), defaults)
        published = _merge_texts(load_texts(values.get("published_texts")), defaults)
        changes = {
            "draft_texts": dump_texts(draft),
            "published_texts": dump_texts(published),
        }
        if changes["draft_texts"] != str(values.get("draft_texts") or "") or changes["published_texts"] != str(values.get("published_texts") or ""):
            _upsert_single(frappe, "revision", str(int(values.get("revision") or 0) + 1))
            for field, value in changes.items():
                _upsert_single(frappe, field, value)
        return
    payload = dump_texts(default_texts())
    now = frappe.utils.now()
    previous = getattr(frappe.flags, SERVICE_FLAG, False)
    setattr(frappe.flags, SERVICE_FLAG, True)
    try:
        frappe.get_doc(
            {
                "doctype": "Customer Bot Settings",
                "enabled": 0,
                "revision": 1,
                "draft_texts": payload,
                "published_texts": payload,
                "published_on": now,
                "published_by": "Administrator",
            }
        ).insert(ignore_permissions=True)
    finally:
        setattr(frappe.flags, SERVICE_FLAG, previous)


def _merge_texts(existing: dict[str, str] | None, defaults: dict[str, str]) -> dict[str, str]:
    """Add new catalog keys while preserving every existing customization."""

    return {**defaults, **(existing or {})}


def _upsert_single(frappe: object, field: str, value: str) -> None:
    db = frappe.db  # type: ignore[attr-defined]
    db.sql(
        "update `tabSingles` set value=%s where doctype=%s and field=%s",
        (value, "Customer Bot Settings", field),
    )
    if int(db._cursor.rowcount) == 1:
        return
    db.sql(
        "insert into `tabSingles` (doctype, field, value) values (%s, %s, %s)",
        ("Customer Bot Settings", field, value),
    )
