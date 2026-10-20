"""Install customer-bot settings once, without replacing a saved copy.

The bot stays off. Repeated migrate repairs the permission column and leaves
an existing draft, published copy, and switch untouched.
"""

from __future__ import annotations


def execute() -> None:
    import frappe

    from almdina_erp.almdina_erp.domain.customer_bot.message_defaults import default_texts
    from almdina_erp.almdina_erp.domain.customer_bot.message_templates import dump_texts
    from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_settings_records import (
        SERVICE_FLAG,
    )
    from almdina_erp.almdina_erp.infrastructure.frappe.permission_type_sync import (
        sync_permission_types,
    )

    sync_permission_types()
    # A Single has no table of its own. DocType existence is not a saved copy.
    if frappe.db.sql(
        "select 1 from `tabSingles` where doctype=%s and field='revision' limit 1",
        ("Customer Bot Settings",),
    ):
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
