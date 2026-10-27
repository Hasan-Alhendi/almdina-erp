"""Idempotent schema that install and migrate must both leave behind.

``bench new-site`` and ``bench install-app`` mark every patch complete without
executing it. A row in Patch Log is therefore not evidence that a column or
index exists. These checks run from ``after_install`` and ``after_migrate``.
They do not run on the inbound message path.
"""

from __future__ import annotations

import frappe

REPLY_INTENT_DOCTYPE = "Customer Bot Reply Intent"
CONVERSATION_DOCTYPE = "Customer Bot Conversation"
EVENT_DOCTYPE = "Customer Bot Inbound Event"
SESSION_UNIQUE_INDEXES = (
    (
        CONVERSATION_DOCTYPE,
        "unique_customer_bot_conversation",
        ("connection_ref", "conversation_id", "sender_id"),
    ),
    (
        EVENT_DOCTYPE,
        "unique_customer_bot_inbound_event",
        ("connection_ref", "provider_event_id"),
    ),
)
REPLY_UNIQUE_INDEXES = (
    ("unique_customer_bot_reply_id", ("reply_id",)),
    (
        "unique_customer_bot_reply_intent",
        ("connection_ref", "provider_event_id", "sequence"),
    ),
)


def ensure_customer_bot_reply_unique_indexes() -> None:
    """Add the reply-intent unique keys when the table exists and they do not.

    The check uses ``SHOW INDEX`` on the current site database. Frappe's
    ``add_unique`` looks up ``information_schema`` by table name alone, so a
    constraint on another site can hide a missing index here.
    """

    if not frappe.db.table_exists(REPLY_INTENT_DOCTYPE):
        return
    table_name = f"tab{REPLY_INTENT_DOCTYPE}"
    for index_name, columns in REPLY_UNIQUE_INDEXES:
        if frappe.db.has_index(table_name, index_name):
            continue
        column_sql = ", ".join(f"`{column}`" for column in columns)
        frappe.db.sql_ddl(
            f"alter table `{table_name}` add unique `{index_name}` ({column_sql})"
        )


def ensure_customer_bot_session_unique_indexes() -> None:
    """Add conversation and inbound-event unique keys from the live schema.

    The patch that first declared them uses ``add_unique``, which can treat an
    index on another site as proof this site already has it. Install also
    marks that patch complete without running it.
    """

    for doctype, index_name, columns in SESSION_UNIQUE_INDEXES:
        if not frappe.db.table_exists(doctype):
            continue
        table_name = f"tab{doctype}"
        if frappe.db.has_index(table_name, index_name):
            continue
        column_sql = ", ".join(f"`{column}`" for column in columns)
        frappe.db.sql_ddl(
            f"alter table `{table_name}` add unique `{index_name}` ({column_sql})"
        )


def ensure_customer_bot_operation_defaults() -> None:
    """Store an explicit stopped decision when the single has no decision yet.

    Does not read or write site_config, and does not change a saved running
    decision.
    """

    if not frappe.db.exists("DocType", "Customer Bot Settings"):
        return
    if not frappe.get_meta("Customer Bot Settings").has_field("operation_decision"):
        return
    current = str(frappe.db.get_single_value("Customer Bot Settings", "operation_decision") or "").strip()
    if current in {"stopped", "running"}:
        return
    from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_settings_records import (
        SERVICE_FLAG,
    )

    previous = getattr(frappe.flags, SERVICE_FLAG, False)
    setattr(frappe.flags, SERVICE_FLAG, True)
    try:
        frappe.db.set_single_value("Customer Bot Settings", "operation_decision", "stopped")
        state = str(frappe.db.get_single_value("Customer Bot Settings", "operation_state") or "").strip()
        if not state:
            frappe.db.set_single_value("Customer Bot Settings", "operation_state", "stopped")
        frappe.db.commit()
    finally:
        setattr(frappe.flags, SERVICE_FLAG, previous)
