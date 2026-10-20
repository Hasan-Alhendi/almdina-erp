"""Add option-2 message keys without replacing saved customer-bot text."""

from __future__ import annotations


def execute() -> None:
    import frappe

    from almdina_erp.almdina_erp.domain.customer_bot.message_defaults import default_texts
    from almdina_erp.almdina_erp.domain.customer_bot.message_templates import (
        dump_texts,
        load_texts,
    )
    from almdina_erp.patches.v1_0.install_customer_bot_settings import _merge_texts

    doctype = "Customer Bot Settings"
    rows = frappe.db.sql(
        "select field, value from `tabSingles` where doctype=%s and field in ('revision', 'draft_texts', 'published_texts')",
        (doctype,),
        as_dict=True,
    )
    values = {row.field: row.value for row in rows}
    if "revision" not in values:
        return

    defaults = default_texts()
    payloads = {
        "draft_texts": dump_texts(_merge_texts(load_texts(values.get("draft_texts")), defaults)),
        "published_texts": dump_texts(_merge_texts(load_texts(values.get("published_texts")), defaults)),
    }
    if all(payloads[field] == str(values.get(field) or "") for field in payloads):
        return

    frappe.db.sql(
        "update `tabSingles` set value=%s where doctype=%s and field='revision'",
        (str(int(values.get("revision") or 0) + 1), doctype),
    )
    for field, value in payloads.items():
        frappe.db.sql(
            "update `tabSingles` set value=%s where doctype=%s and field=%s",
            (value, doctype, field),
        )


__all__ = ["execute"]
