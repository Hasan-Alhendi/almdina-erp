"""Local admin helpers for customer-bot ops / pilot / readiness (bench execute).

No HTTP endpoint. Never prints or returns webhook secrets, API keys, or tokens.
Does not create users or API keys. Does not register OpenWA webhooks. Does not
create, QR-link, stop, or log out an OpenWA session.
"""

from __future__ import annotations

from typing import Any

import frappe
from frappe.utils.password import set_encrypted_password

from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_inbound_connection import (
    DOCTYPE,
)
from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_ops import (
    arm_customer_bot_transport,
    disarm_customer_bot_transport,
    ops_status,
    refresh_ops_start_cutoff,
    set_customer_bot_ops_mode,
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
from almdina_erp.almdina_erp.infrastructure.whatsapp.customer_bot_ops_config import (
    OPS_MODE_OFF,
    OPS_MODE_PILOT,
    OPS_MODE_PRODUCTION,
)


def configure_openwa_inbound_connection(
    connection_ref: str,
    session_id: str,
    webhook_secret: str,
) -> dict[str, Any]:
    """Store OpenWA inbound connection values on Customer Bot Settings.

    ``webhook_secret`` must be at least 16 characters (OpenWA HMAC floor).
    The secret is stored encrypted and is never returned. Changing the
    connection refreshes the ops start cutoff and disarms transport so prior
    intents cannot send under the old connection.
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
    ops = refresh_ops_start_cutoff(disarm=True)
    return {
        "ok": True,
        "doctype": DOCTYPE,
        "connection_ref": ref,
        "session_id": session,
        "webhook_secret_configured": True,
        "ops": ops,
    }


def enable_pilot(phone_e164: str, arm_transport: int | bool = 0) -> dict[str, Any]:
    """Enable the single-phone pilot. Default keeps transport disarmed."""

    _require_console_admin()
    return enable_customer_bot_pilot(
        phone_e164,
        arm_transport=bool(arm_transport),
    )


def disable_pilot() -> dict[str, Any]:
    """Disable pilot / set ops mode off and disarm transport."""

    _require_console_admin()
    return disable_customer_bot_pilot()


def arm_pilot_transport() -> dict[str, Any]:
    """Arm live transport for the current ready ops mode."""

    _require_console_admin()
    return arm_customer_bot_pilot_transport()


def disarm_pilot_transport() -> dict[str, Any]:
    """Disarm transport without clearing the phone / mode gate."""

    _require_console_admin()
    return disarm_customer_bot_pilot_transport()


def show_pilot_status() -> dict[str, Any]:
    """Return pilot / ops status without secrets."""

    _require_console_admin()
    status = pilot_status()
    status["live_module_enabled"] = _live_module_flag()
    status["transport_may_run"] = _transport_may_run_snapshot()
    status["ops"] = ops_status()
    return status


def set_ops_mode(
    mode: str,
    pilot_phone_e164: str | None = None,
    arm_transport: int | bool = 0,
) -> dict[str, Any]:
    """Set ``off`` / ``pilot`` / ``production`` with a fresh start cutoff.

    Default keeps transport disarmed. Never auto-enables production on migrate.
    """

    _require_console_admin()
    normalized = str(mode or "").strip().lower()
    if normalized not in {OPS_MODE_OFF, OPS_MODE_PILOT, OPS_MODE_PRODUCTION}:
        raise ValueError(f"invalid_ops_mode:{mode!r}")
    return set_customer_bot_ops_mode(
        normalized,
        pilot_phone_e164=pilot_phone_e164,
        arm_transport=bool(arm_transport),
    )


def arm_transport() -> dict[str, Any]:
    """Arm transport when ops is ready (pilot or production)."""

    _require_console_admin()
    return arm_customer_bot_transport()


def disarm_transport() -> dict[str, Any]:
    """Disarm transport without changing ops mode."""

    _require_console_admin()
    return disarm_customer_bot_transport()


def show_ops_status() -> dict[str, Any]:
    """Return ops status without secrets."""

    _require_console_admin()
    status = ops_status()
    status["live_module_enabled"] = _live_module_flag()
    return status


def check_readiness(probe_network: int | bool = 0) -> dict[str, Any]:
    """Read-only readiness report. Does not send or create bot rows."""

    _require_console_admin()
    from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_readiness import (
        check_customer_bot_readiness,
    )

    return check_customer_bot_readiness(probe_network=bool(probe_network))


def _live_module_flag() -> bool:
    from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_reply_delivery import (
        LIVE_REPLY_DELIVERY_ENABLED,
    )

    return bool(LIVE_REPLY_DELIVERY_ENABLED)


def _transport_may_run_snapshot() -> bool:
    from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_ops import (
        ops_transport_may_run,
    )
    from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_reply_delivery import (
        LIVE_REPLY_DELIVERY_ENABLED,
    )

    return ops_transport_may_run(live_module_enabled=bool(LIVE_REPLY_DELIVERY_ENABLED))


def _require_console_admin() -> None:
    user = getattr(frappe.session, "user", None)
    if user not in {"Administrator"}:
        frappe.throw("customer bot ops admin requires Administrator", frappe.PermissionError)


__all__ = [
    "arm_pilot_transport",
    "arm_transport",
    "check_readiness",
    "configure_openwa_inbound_connection",
    "disable_pilot",
    "disarm_pilot_transport",
    "disarm_transport",
    "enable_pilot",
    "set_ops_mode",
    "show_ops_status",
    "show_pilot_status",
]
