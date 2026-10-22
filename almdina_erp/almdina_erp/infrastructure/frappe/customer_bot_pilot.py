"""Server-side customer-bot pilot gate (site_config only).

Lab UI ``enabled`` never arms live transport. The webhook body never supplies
pilot values. ``LIVE_REPLY_DELIVERY_ENABLED`` alone cannot bypass the phone
gate: transport also requires a ready pilot and an armed transport flag.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from almdina_erp.almdina_erp.domain.customer_bot.phone_number import CustomerPhoneError
from almdina_erp.almdina_erp.infrastructure.whatsapp.customer_bot_pilot_config import (
    CustomerBotPilotConfig,
    parse_pilot_phone,
    pilot_phone_or_none,
)

CONF_ENABLED = "customer_bot_pilot_enabled"
CONF_PHONE = "customer_bot_pilot_phone_e164"
CONF_STARTED_AT = "customer_bot_pilot_started_at"
CONF_TRANSPORT_ARMED = "customer_bot_pilot_transport_armed"

REASON_PILOT_INACTIVE = "pilot_inactive"
REASON_PILOT_PHONE_MISMATCH = "pilot_phone_mismatch"
REASON_PILOT_TOO_OLD = "pilot_before_start"


def load_customer_bot_pilot() -> CustomerBotPilotConfig:
    """Read the current pilot gate from ``frappe.conf`` (defaults: off)."""

    conf = _conf_mapping()
    enabled = _truthy(conf.get(CONF_ENABLED))
    phone = pilot_phone_or_none(conf.get(CONF_PHONE))
    started_at = _parse_iso(conf.get(CONF_STARTED_AT))
    transport_armed = _truthy(conf.get(CONF_TRANSPORT_ARMED))
    if enabled and phone is None:
        # Fail closed: enabled without a valid phone admits nobody.
        return CustomerBotPilotConfig(
            enabled=True,
            phone_e164=None,
            started_at=started_at,
            transport_armed=False,
        )
    return CustomerBotPilotConfig(
        enabled=enabled,
        phone_e164=phone,
        started_at=started_at,
        transport_armed=transport_armed,
    )


def pilot_transport_may_run(*, live_module_enabled: bool) -> bool:
    """True only when live is armed and the pilot gate is ready.

    ``live_module_enabled`` is the code kill-switch. Site config may also arm
    transport for a local pilot without editing the module constant. Neither
    path skips the phone / start-time gate on individual intents.
    """

    pilot = load_customer_bot_pilot()
    if not pilot.is_ready:
        return False
    if not (live_module_enabled or pilot.transport_armed):
        return False
    return True


def enable_customer_bot_pilot(
    phone_e164: str,
    *,
    arm_transport: bool = False,
    started_at: datetime | None = None,
) -> dict[str, Any]:
    """Activate the pilot for one E.164 number. Invalid phone refuses enablement.

    Sets a fresh ``started_at`` so older reply intents stay unsent. Does not
    delete rows or rewrite ``accepted`` / ``unknown`` outcomes. Transport stays
    off unless ``arm_transport`` is explicitly True.
    """

    try:
        phone = parse_pilot_phone(phone_e164)
    except CustomerPhoneError as error:
        raise ValueError(f"invalid_pilot_phone:{error.code}") from error
    if started_at is None:
        started_at = datetime.now(timezone.utc)
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)
    stamp = started_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    _write_conf(CONF_PHONE, phone)
    _write_conf(CONF_STARTED_AT, stamp)
    _write_conf(CONF_ENABLED, 1)
    _write_conf(CONF_TRANSPORT_ARMED, 1 if arm_transport else 0)
    _refresh_conf()
    return pilot_status()


def disable_customer_bot_pilot() -> dict[str, Any]:
    """Stop the pilot and disarm transport. Keeps phone/start for audit."""

    _write_conf(CONF_ENABLED, 0)
    _write_conf(CONF_TRANSPORT_ARMED, 0)
    _refresh_conf()
    return pilot_status()


def arm_customer_bot_pilot_transport() -> dict[str, Any]:
    """Allow the worker to start gateway calls when the pilot is already ready."""

    pilot = load_customer_bot_pilot()
    if not pilot.is_ready:
        raise ValueError("pilot_not_ready")
    _write_conf(CONF_TRANSPORT_ARMED, 1)
    _refresh_conf()
    return pilot_status()


def disarm_customer_bot_pilot_transport() -> dict[str, Any]:
    """Block new gateway calls without clearing the pilot phone gate."""

    _write_conf(CONF_TRANSPORT_ARMED, 0)
    _refresh_conf()
    return pilot_status()


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
    }


def intent_pilot_cancel_reason(
    pilot: CustomerBotPilotConfig,
    *,
    normalized_phone: str | None,
    created_on: datetime | None,
) -> str | None:
    """Return a cancel reason when a claimed intent must not leave the outbox."""

    if not pilot.is_ready:
        return REASON_PILOT_INACTIVE
    if not pilot.admits_phone(normalized_phone):
        return REASON_PILOT_PHONE_MISMATCH
    if not pilot.admits_intent(normalized_phone=normalized_phone, created_on=created_on):
        return REASON_PILOT_TOO_OLD
    return None


def _truthy(value: object) -> bool:
    if value is True or value == 1:
        return True
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return False


def _parse_iso(value: object) -> datetime | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _conf_mapping() -> dict[str, Any]:
    try:
        import frappe
    except ImportError:
        return {}
    try:
        conf = getattr(frappe, "conf", None)
    except Exception:
        return {}
    if conf is None:
        return {}
    try:
        return dict(conf)
    except Exception:
        try:
            return {key: conf.get(key) for key in (
                CONF_ENABLED,
                CONF_PHONE,
                CONF_STARTED_AT,
                CONF_TRANSPORT_ARMED,
            )}
        except Exception:
            return {}


def _write_conf(key: str, value: object) -> None:
    from frappe.installer import update_site_config

    update_site_config(key, value)


def _refresh_conf() -> None:
    try:
        import frappe
    except ImportError:
        return
    try:
        frappe.clear_cache()
    except Exception:
        pass
    # update_site_config writes disk; keep the in-process conf aligned.
    try:
        site = getattr(frappe.local, "site", None)
        if site:
            fresh = frappe.get_site_config()
            frappe.local.conf = fresh
            frappe.conf = fresh
    except Exception:
        pass


__all__ = [
    "CONF_ENABLED",
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
