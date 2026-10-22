"""Load the trusted OpenWA inbound connection from Customer Bot Settings.

The webhook body never chooses ``connection_ref``, the expected session id, or
the HMAC secret. Password storage follows the same Frappe encrypted-field path
used elsewhere in the project. Empty values mean reception is closed.
"""

from __future__ import annotations

import frappe

from almdina_erp.almdina_erp.infrastructure.whatsapp.customer_bot_inbound_config import (
    OpenWAInboundConnectionConfig,
)

DOCTYPE = "Customer Bot Settings"
_CONNECTION_REF_FIELD = "openwa_connection_ref"
_SESSION_ID_FIELD = "openwa_session_id"
_SECRET_FIELD = "openwa_webhook_secret"


def load_openwa_inbound_connection() -> OpenWAInboundConnectionConfig | None:
    """Return the configured connection, or ``None`` when any required value is missing."""

    rows = frappe.db.sql(
        "select field, value from `tabSingles` where doctype=%s and field in %s",
        (DOCTYPE, (_CONNECTION_REF_FIELD, _SESSION_ID_FIELD)),
        as_dict=True,
    )
    values = {str(row.field): str(row.value or "").strip() for row in rows or ()}
    connection_ref = values.get(_CONNECTION_REF_FIELD, "")
    session_id = values.get(_SESSION_ID_FIELD, "")
    secret = ""
    try:
        document = frappe.get_single(DOCTYPE)
        secret = str(document.get_password(_SECRET_FIELD, raise_exception=False) or "").strip()
    except Exception:
        secret = ""
    config = OpenWAInboundConnectionConfig(
        connection_ref=connection_ref,
        session_id=session_id,
        webhook_secret=secret,
    )
    if not config.is_complete:
        return None
    return config


__all__ = ["DOCTYPE", "load_openwa_inbound_connection"]
