"""Local admin helpers for customer-bot pilot prep (bench execute only).

No HTTP endpoint. Never prints or returns webhook secrets, API keys, or tokens.
Does not create users or API keys. Does not register OpenWA webhooks.
"""

from __future__ import annotations

from typing import Any

import frappe
from frappe.utils.password import set_encrypted_password

from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_inbound_connection import (
    DOCTYPE,
)
from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_pilot import (
    arm_customer_bot_pilot_transport,
    disable_customer_bot_pilot,
    disarm_customer_bot_pilot_transport,
    enable_customer_bot_pilot,
    pilot_status,
)
from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_settings_records import (
    SERVICE_FLAG,
)


def configure_openwa_inbound_connection(
    connection_ref: str,
    session_id: str,
    webhook_secret: str,
) -> dict[str, Any]:
    """Store OpenWA inbound connection values on Customer Bot Settings.

    ``webhook_secret`` must be at least 16 characters (OpenWA HMAC floor).
    The secret is stored encrypted and is never returned.
    """

    _require_console_admin()
    ref = str(connection_ref or "").strip()
    session = str(session_id or "").strip()
    secret = str(webhook_secret or "")
    if not ref or not session:
        raise ValueError("connection_ref_and_session_id_required")
    if len(secret) < 16:
        raise ValueError("webhook_secret_too_short")
    previous = getattr(frappe.flags, SERVICE_FLAG, False)
    setattr(frappe.flags, SERVICE_FLAG, True)
    try:
        frappe.db.set_single_value(DOCTYPE, "openwa_connection_ref", ref)
        frappe.db.set_single_value(DOCTYPE, "openwa_session_id", session)
        set_encrypted_password(DOCTYPE, DOCTYPE, secret, fieldname="openwa_webhook_secret")
        frappe.clear_cache()
        frappe.db.commit()
    finally:
        setattr(frappe.flags, SERVICE_FLAG, previous)
    return {
        "ok": True,
        "doctype": DOCTYPE,
        "connection_ref": ref,
        "session_id": session,
        "webhook_secret_configured": True,
    }


def enable_pilot(phone_e164: str, arm_transport: int | bool = 0) -> dict[str, Any]:
    """Enable the single-phone pilot. Default keeps transport disarmed."""

    _require_console_admin()
    return enable_customer_bot_pilot(
        phone_e164,
        arm_transport=bool(arm_transport),
    )


def disable_pilot() -> dict[str, Any]:
    """Disable pilot and disarm transport."""

    _require_console_admin()
    return disable_customer_bot_pilot()


def arm_pilot_transport() -> dict[str, Any]:
    """Arm live transport for the current ready pilot (still needs LIVE or this flag)."""

    _require_console_admin()
    return arm_customer_bot_pilot_transport()


def disarm_pilot_transport() -> dict[str, Any]:
    """Disarm transport without clearing the phone gate."""

    _require_console_admin()
    return disarm_customer_bot_pilot_transport()


def show_pilot_status() -> dict[str, Any]:
    """Return pilot status without secrets."""

    _require_console_admin()
    status = pilot_status()
    status["live_module_enabled"] = _live_module_flag()
    status["transport_may_run"] = _transport_may_run_snapshot()
    return status


def _live_module_flag() -> bool:
    from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_reply_delivery import (
        LIVE_REPLY_DELIVERY_ENABLED,
    )

    return bool(LIVE_REPLY_DELIVERY_ENABLED)


def _transport_may_run_snapshot() -> bool:
    from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_pilot import (
        pilot_transport_may_run,
    )
    from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_reply_delivery import (
        LIVE_REPLY_DELIVERY_ENABLED,
    )

    return pilot_transport_may_run(live_module_enabled=bool(LIVE_REPLY_DELIVERY_ENABLED))


def _require_console_admin() -> None:
    user = getattr(frappe.session, "user", None)
    if user not in {"Administrator"}:
        # bench execute typically runs as Administrator; reject other contexts.
        frappe.throw("customer bot pilot admin requires Administrator", frappe.PermissionError)


__all__ = [
    "arm_pilot_transport",
    "configure_openwa_inbound_connection",
    "disable_pilot",
    "disarm_pilot_transport",
    "enable_pilot",
    "show_pilot_status",
]
