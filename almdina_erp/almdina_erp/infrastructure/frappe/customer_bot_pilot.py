"""Server-side customer-bot pilot gate (compat layer over ops mode).

Prefer ``customer_bot_ops`` for new call sites. This module keeps the pilot
admin API and ``CustomerBotPilotConfig`` shape used by existing tests. Lab UI
``enabled`` never arms live transport. ``LIVE_REPLY_DELIVERY_ENABLED`` alone
cannot bypass the phone gate.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from almdina_erp.almdina_erp.domain.customer_bot.phone_number import CustomerPhoneError
from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_ops import (
    CONF_OPS_MODE,
    CONF_PILOT_ENABLED,
    CONF_PILOT_PHONE,
    CONF_PILOT_STARTED_AT,
    CONF_PILOT_TRANSPORT_ARMED,
    REASON_PILOT_INACTIVE,
    REASON_PILOT_PHONE_MISMATCH,
    REASON_PILOT_TOO_OLD,
    arm_customer_bot_transport,
    disarm_customer_bot_transport,
    intent_ops_cancel_reason,
    load_customer_bot_ops,
    ops_transport_may_run,
    set_customer_bot_ops_mode,
)
from almdina_erp.almdina_erp.infrastructure.whatsapp.customer_bot_ops_config import (
    OPS_MODE_PILOT,
)
from almdina_erp.almdina_erp.infrastructure.whatsapp.customer_bot_pilot_config import (
    CustomerBotPilotConfig,
    parse_pilot_phone,
    pilot_phone_or_none,
)

# Re-export legacy key names for callers / docs.
CONF_ENABLED = CONF_PILOT_ENABLED
CONF_PHONE = CONF_PILOT_PHONE
CONF_STARTED_AT = CONF_PILOT_STARTED_AT
CONF_TRANSPORT_ARMED = CONF_PILOT_TRANSPORT_ARMED


def load_customer_bot_pilot() -> CustomerBotPilotConfig:
    """Read the pilot slice of the ops gate (defaults: off)."""

    ops = load_customer_bot_ops()
    enabled = ops.mode == OPS_MODE_PILOT
    return CustomerBotPilotConfig(
        enabled=enabled,
        phone_e164=ops.pilot_phone_e164 if enabled else pilot_phone_or_none(
            _raw_pilot_phone()
        ),
        started_at=ops.started_at if enabled else None,
        transport_armed=ops.transport_armed if enabled else False,
    )


def pilot_transport_may_run(*, live_module_enabled: bool) -> bool:
    """True only when live is armed and the effective ops gate is ready."""

    return ops_transport_may_run(live_module_enabled=live_module_enabled)


def enable_customer_bot_pilot(
    phone_e164: str,
    *,
    arm_transport: bool = False,
    started_at: datetime | None = None,
) -> dict[str, Any]:
    """Activate the single-phone pilot. Invalid phone refuses enablement."""

    try:
        parse_pilot_phone(phone_e164)
    except CustomerPhoneError as error:
        raise ValueError(f"invalid_pilot_phone:{error.code}") from error
    set_customer_bot_ops_mode(
        OPS_MODE_PILOT,
        pilot_phone_e164=phone_e164,
        arm_transport=arm_transport,
        started_at=started_at,
    )
    return pilot_status()


def disable_customer_bot_pilot() -> dict[str, Any]:
    """Stop the pilot and disarm transport. Keeps phone/start for audit."""

    set_customer_bot_ops_mode("off", arm_transport=False)
    return pilot_status()


def arm_customer_bot_pilot_transport() -> dict[str, Any]:
    """Allow the worker to start gateway calls when the pilot is already ready."""

    return arm_customer_bot_transport()


def disarm_customer_bot_pilot_transport() -> dict[str, Any]:
    """Block new gateway calls without clearing the pilot phone gate."""

    return disarm_customer_bot_transport()


def pilot_status() -> dict[str, Any]:
    """Operator-safe snapshot (no secrets)."""

    pilot = load_customer_bot_pilot()
    return {
        "enabled": pilot.enabled,
        "is_ready": pilot.is_ready,
        "phone_e164": pilot.phone_e164,
        "started_at": (
            pilot.started_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
            if pilot.started_at
            else None
        ),
        "transport_armed": pilot.transport_armed,
        "ops_mode": load_customer_bot_ops().mode,
    }


def intent_pilot_cancel_reason(
    pilot: CustomerBotPilotConfig,
    *,
    normalized_phone: str | None,
    created_on: datetime | None,
) -> str | None:
    """Return a cancel reason when a claimed intent must not leave the outbox."""

    from almdina_erp.almdina_erp.infrastructure.whatsapp.customer_bot_ops_config import (
        CustomerBotOpsConfig,
        OPS_MODE_OFF,
        OPS_MODE_PILOT,
    )

    if not pilot.enabled:
        ops = CustomerBotOpsConfig(
            mode=OPS_MODE_OFF,
            pilot_phone_e164=pilot.phone_e164,
            started_at=pilot.started_at,
            transport_armed=False,
            transport_live=False,
        )
    else:
        ops = CustomerBotOpsConfig(
            mode=OPS_MODE_PILOT,
            pilot_phone_e164=pilot.phone_e164,
            started_at=pilot.started_at,
            transport_armed=pilot.transport_armed,
            transport_live=False,
        )
    return intent_ops_cancel_reason(
        ops,
        normalized_phone=normalized_phone,
        created_on=created_on,
    )


def _raw_pilot_phone() -> object:
    try:
        import frappe
    except ImportError:
        return None
    try:
        return getattr(frappe.conf, CONF_PILOT_PHONE, None)
    except Exception:
        return None


__all__ = [
    "CONF_ENABLED",
    "CONF_OPS_MODE",
    "CONF_PHONE",
    "CONF_STARTED_AT",
    "CONF_TRANSPORT_ARMED",
    "REASON_PILOT_INACTIVE",
    "REASON_PILOT_PHONE_MISMATCH",
    "REASON_PILOT_TOO_OLD",
    "arm_customer_bot_pilot_transport",
    "disable_customer_bot_pilot",
    "disarm_customer_bot_pilot_transport",
    "enable_customer_bot_pilot",
    "intent_pilot_cancel_reason",
    "load_customer_bot_pilot",
    "pilot_status",
    "pilot_transport_may_run",
]
