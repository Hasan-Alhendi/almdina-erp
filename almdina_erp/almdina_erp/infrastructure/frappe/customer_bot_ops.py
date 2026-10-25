"""Server-side customer-bot operations mode (site_config only).

Lab UI ``enabled`` never arms live transport. The webhook body never supplies
ops values. Transport requires a ready ops mode plus an explicit server arm
(``customer_bot_transport_armed`` / legacy pilot arm) or
``customer_bot_transport_live``. The deprecated module constant
``LIVE_REPLY_DELIVERY_ENABLED`` remains a hard ``False`` and cannot open
production by itself.

Mode resolution (fail closed):

1. Explicit ``customer_bot_ops_mode`` when it is ``off`` / ``pilot`` /
   ``production``.
2. Else legacy ``customer_bot_pilot_enabled`` truthy → ``pilot``.
3. Else → ``off``.

Missing or incomplete pilot settings never resolve to ``production``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from almdina_erp.almdina_erp.domain.customer_bot.phone_number import CustomerPhoneError
from almdina_erp.almdina_erp.infrastructure.whatsapp.customer_bot_ops_config import (
    OPS_MODE_OFF,
    OPS_MODE_PILOT,
    OPS_MODE_PRODUCTION,
    OPS_MODES,
    CustomerBotOpsConfig,
)
from almdina_erp.almdina_erp.infrastructure.whatsapp.customer_bot_pilot_config import (
    parse_pilot_phone,
    pilot_phone_or_none,
)

# Explicit ops mode (preferred).
CONF_OPS_MODE = "customer_bot_ops_mode"
# Production / unified start cutoff. Pilot still prefers the legacy stamp below.
CONF_OPS_STARTED_AT = "customer_bot_ops_started_at"
# Preferred transport arm (aliases legacy pilot arm).
CONF_TRANSPORT_ARMED = "customer_bot_transport_armed"
# Server-side live transport allow (replaces editing LIVE_REPLY_DELIVERY_ENABLED).
CONF_TRANSPORT_LIVE = "customer_bot_transport_live"

# Legacy pilot keys (still authoritative for phone + pilot started_at).
CONF_PILOT_ENABLED = "customer_bot_pilot_enabled"
CONF_PILOT_PHONE = "customer_bot_pilot_phone_e164"
CONF_PILOT_STARTED_AT = "customer_bot_pilot_started_at"
CONF_PILOT_TRANSPORT_ARMED = "customer_bot_pilot_transport_armed"

REASON_OPS_INACTIVE = "ops_inactive"
REASON_OPS_PHONE_MISMATCH = "ops_phone_mismatch"
REASON_OPS_TOO_OLD = "ops_before_start"
# Keep pilot reason codes for existing callers / tests.
REASON_PILOT_INACTIVE = "pilot_inactive"
REASON_PILOT_PHONE_MISMATCH = "pilot_phone_mismatch"
REASON_PILOT_TOO_OLD = "pilot_before_start"


class CustomerBotOpsTransitionError(RuntimeError):
    """An ops transition did not finish, so it must not be reported as applied."""


def resolve_ops_mode(conf: dict[str, Any] | None = None) -> str:
    """Return the effective ops mode. Never defaults to production."""

    mapping = conf if conf is not None else _conf_mapping()
    raw = mapping.get(CONF_OPS_MODE)
    if isinstance(raw, str):
        mode = raw.strip().lower()
        if mode in OPS_MODES:
            return mode
    if _truthy(mapping.get(CONF_PILOT_ENABLED)):
        return OPS_MODE_PILOT
    return OPS_MODE_OFF


def load_customer_bot_ops() -> CustomerBotOpsConfig:
    """Read the current ops gate from ``frappe.conf`` (defaults: off)."""

    conf = _conf_mapping()
    mode = resolve_ops_mode(conf)
    phone = pilot_phone_or_none(conf.get(CONF_PILOT_PHONE))
    transport_armed = _truthy(conf.get(CONF_TRANSPORT_ARMED)) or _truthy(
        conf.get(CONF_PILOT_TRANSPORT_ARMED)
    )
    transport_live = _truthy(conf.get(CONF_TRANSPORT_LIVE))
    if mode == OPS_MODE_PILOT:
        started_at = _parse_iso(conf.get(CONF_PILOT_STARTED_AT))
        if phone is None:
            # Fail closed: pilot mode without a valid phone admits nobody.
            return CustomerBotOpsConfig(
                mode=OPS_MODE_PILOT,
                pilot_phone_e164=None,
                started_at=started_at,
                transport_armed=False,
                transport_live=transport_live,
            )
        return CustomerBotOpsConfig(
            mode=OPS_MODE_PILOT,
            pilot_phone_e164=phone,
            started_at=started_at,
            transport_armed=transport_armed,
            transport_live=transport_live,
        )
    if mode == OPS_MODE_PRODUCTION:
        started_at = _parse_iso(conf.get(CONF_OPS_STARTED_AT))
        if started_at is None:
            # Do not fall back to a pilot stamp: opening production must set a
            # fresh cutoff so pilot/dev intents are not revived.
            started_at = None
        return CustomerBotOpsConfig(
            mode=OPS_MODE_PRODUCTION,
            pilot_phone_e164=phone,
            started_at=started_at,
            transport_armed=transport_armed,
            transport_live=transport_live,
        )
    return CustomerBotOpsConfig(
        mode=OPS_MODE_OFF,
        pilot_phone_e164=phone,
        started_at=_parse_iso(conf.get(CONF_OPS_STARTED_AT))
        or _parse_iso(conf.get(CONF_PILOT_STARTED_AT)),
        transport_armed=False,
        transport_live=transport_live,
    )


def ops_transport_may_run(*, live_module_enabled: bool = False) -> bool:
    """True only when ops is ready and transport is explicitly allowed.

    ``live_module_enabled`` is the deprecated code kill-switch (always False in
    production code). Site ``customer_bot_transport_live`` or the arm flag may
    allow transport without editing the module. Neither path skips phone /
    start-time gates on individual intents.
    """

    ops = load_customer_bot_ops()
    if not ops.is_ready:
        return False
    if not (live_module_enabled or ops.transport_live or ops.transport_armed):
        return False
    return True


def intent_ops_cancel_reason(
    ops: CustomerBotOpsConfig,
    *,
    normalized_phone: str | None,
    created_on: datetime | None,
) -> str | None:
    """Return a cancel reason when a claimed intent must not leave the outbox."""

    if not ops.is_ready:
        if ops.mode == OPS_MODE_PILOT:
            return REASON_PILOT_INACTIVE
        return REASON_OPS_INACTIVE
    if not ops.admits_inbound_phone(normalized_phone):
        if ops.mode == OPS_MODE_PILOT:
            return REASON_PILOT_PHONE_MISMATCH
        return REASON_OPS_PHONE_MISMATCH
    if not ops.admits_intent(normalized_phone=normalized_phone, created_on=created_on):
        if ops.mode == OPS_MODE_PILOT:
            return REASON_PILOT_TOO_OLD
        return REASON_OPS_TOO_OLD
    return None


def set_customer_bot_ops_mode(
    mode: str,
    *,
    pilot_phone_e164: str | None = None,
    arm_transport: bool = False,
    started_at: datetime | None = None,
) -> dict[str, Any]:
    """Set ops mode with a fresh start cutoff. Transport stays off unless armed.

    Does not rewrite ``accepted`` / ``unknown`` rows. Advances acceptance epoch
    so prior conversation cycles cannot keep sending under a new mode.
    """

    normalized = str(mode or "").strip().lower()
    if normalized not in OPS_MODES:
        raise ValueError(f"invalid_ops_mode:{mode!r}")
    if started_at is None:
        started_at = datetime.now(timezone.utc)
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)
    stamp = started_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    phone = None
    if normalized == OPS_MODE_PILOT:
        phone_raw = pilot_phone_e164
        if phone_raw is None:
            phone_raw = _conf_mapping().get(CONF_PILOT_PHONE)
        try:
            phone = parse_pilot_phone(phone_raw)
        except CustomerPhoneError as error:
            raise ValueError(f"invalid_pilot_phone:{error.code}") from error

    # Close transport before any other write. Turning the mode off also
    # happens before the epoch so a database failure cannot leave acceptance
    # and transport open. A new pilot or production window is written only
    # after the epoch advances.
    if normalized == OPS_MODE_OFF or not arm_transport:
        _disarm_transport_keys()
    if normalized == OPS_MODE_OFF:
        _write_conf(CONF_OPS_MODE, OPS_MODE_OFF)
        _write_conf(CONF_PILOT_ENABLED, 0)
    _bump_acceptance_epoch()

    if normalized == OPS_MODE_OFF:
        _refresh_conf()
        return ops_status()
    if normalized == OPS_MODE_PILOT:
        _write_conf(CONF_OPS_MODE, OPS_MODE_PILOT)
        _write_conf(CONF_PILOT_PHONE, phone)
        _write_conf(CONF_PILOT_STARTED_AT, stamp)
        _write_conf(CONF_PILOT_ENABLED, 1)
        _write_conf(CONF_TRANSPORT_ARMED, 1 if arm_transport else 0)
        _write_conf(CONF_PILOT_TRANSPORT_ARMED, 1 if arm_transport else 0)
    else:
        _write_conf(CONF_OPS_MODE, OPS_MODE_PRODUCTION)
        _write_conf(CONF_OPS_STARTED_AT, stamp)
        # Keep legacy pilot_enabled off so resolve never falls back to pilot.
        _write_conf(CONF_PILOT_ENABLED, 0)
        _write_conf(CONF_TRANSPORT_ARMED, 1 if arm_transport else 0)
        _write_conf(CONF_PILOT_TRANSPORT_ARMED, 1 if arm_transport else 0)
    _refresh_conf()
    return ops_status()


def arm_customer_bot_transport() -> dict[str, Any]:
    """Allow the worker to start gateway calls when ops is already ready."""

    ops = load_customer_bot_ops()
    if not ops.is_ready:
        raise ValueError("ops_not_ready")
    _write_conf(CONF_TRANSPORT_ARMED, 1)
    _write_conf(CONF_PILOT_TRANSPORT_ARMED, 1)
    _refresh_conf()
    return ops_status()


def disarm_customer_bot_transport() -> dict[str, Any]:
    """Block new gateway calls without clearing the ops mode gate."""

    _disarm_transport_keys()
    _refresh_conf()
    return ops_status()


def refresh_ops_start_cutoff(*, disarm: bool = True) -> dict[str, Any]:
    """Stamp a new start cutoff (connection / phone change). Keeps mode."""

    ops = load_customer_bot_ops()
    stamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    if disarm:
        _disarm_transport_keys()
    _bump_acceptance_epoch()
    if ops.mode == OPS_MODE_PILOT:
        _write_conf(CONF_PILOT_STARTED_AT, stamp)
    else:
        _write_conf(CONF_OPS_STARTED_AT, stamp)
    _refresh_conf()
    return ops_status()


def ops_status() -> dict[str, Any]:
    """Operator-safe snapshot (no secrets)."""

    ops = load_customer_bot_ops()
    return {
        "mode": ops.mode,
        "is_ready": ops.is_ready,
        "pilot_phone_e164": ops.pilot_phone_e164,
        "started_at": (
            ops.started_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
            if ops.started_at
            else None
        ),
        "transport_armed": ops.transport_armed,
        "transport_live": ops.transport_live,
        "transport_may_run": ops_transport_may_run(live_module_enabled=False),
        "resolved_from_legacy_pilot": (
            CONF_OPS_MODE not in _conf_mapping()
            and _truthy(_conf_mapping().get(CONF_PILOT_ENABLED))
        ),
    }


def _disarm_transport_keys() -> None:
    """Turn off every supported transport switch, including the live site flag."""

    _write_conf(CONF_TRANSPORT_LIVE, 0)
    _write_conf(CONF_TRANSPORT_ARMED, 0)
    _write_conf(CONF_PILOT_TRANSPORT_ARMED, 0)


def _bump_acceptance_epoch() -> int:
    """Advance the settings acceptance epoch so prior cycles cannot keep sending.

    A database failure raises. Callers must not report the transition as applied.
    """

    try:
        import frappe
    except ImportError as error:
        raise CustomerBotOpsTransitionError("acceptance_epoch_unavailable") from error
    doctype = "Customer Bot Settings"
    try:
        rows = _epoch_sql(
            frappe.db,
            """
            select value from `tabSingles`
            where doctype=%s and field='acceptance_epoch'
            for update
            """,
            (doctype,),
        )
        current = int(rows[0].value or 0) if rows else 0
        new_epoch = current + 1
        if rows:
            changed = _epoch_execute(
                frappe.db,
                """
                update `tabSingles`
                set value=%s
                where doctype=%s and field='acceptance_epoch'
                """,
                (str(new_epoch), doctype),
            )
            if changed != 1:
                raise CustomerBotOpsTransitionError("acceptance_epoch_update_failed")
        else:
            _epoch_execute(
                frappe.db,
                """
                insert into `tabSingles` (doctype, field, value)
                values (%s, 'acceptance_epoch', %s)
                """,
                (doctype, str(new_epoch)),
            )
        return new_epoch
    except CustomerBotOpsTransitionError:
        raise
    except Exception as error:
        raise CustomerBotOpsTransitionError("acceptance_epoch_update_failed") from error


def _epoch_sql(database: Any, query: str, params: tuple[object, ...]) -> list[Any]:
    return list(database.sql(query, params, as_dict=True) or [])


def _epoch_execute(database: Any, query: str, params: tuple[object, ...]) -> int:
    database.sql(query, params)
    return int(getattr(getattr(database, "_cursor", None), "rowcount", 0) or 0)


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
        keys = (
            CONF_OPS_MODE,
            CONF_OPS_STARTED_AT,
            CONF_TRANSPORT_ARMED,
            CONF_TRANSPORT_LIVE,
            CONF_PILOT_ENABLED,
            CONF_PILOT_PHONE,
            CONF_PILOT_STARTED_AT,
            CONF_PILOT_TRANSPORT_ARMED,
        )
        try:
            return {key: conf.get(key) for key in keys}
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
    try:
        site = getattr(frappe.local, "site", None)
        if site:
            fresh = frappe.get_site_config()
            frappe.local.conf = fresh
            frappe.conf = fresh
    except Exception:
        pass


__all__ = [
    "CONF_OPS_MODE",
    "CONF_OPS_STARTED_AT",
    "CONF_PILOT_ENABLED",
    "CONF_PILOT_PHONE",
    "CONF_PILOT_STARTED_AT",
    "CONF_PILOT_TRANSPORT_ARMED",
    "CONF_TRANSPORT_ARMED",
    "CONF_TRANSPORT_LIVE",
    "REASON_OPS_INACTIVE",
    "REASON_OPS_PHONE_MISMATCH",
    "REASON_OPS_TOO_OLD",
    "REASON_PILOT_INACTIVE",
    "REASON_PILOT_PHONE_MISMATCH",
    "REASON_PILOT_TOO_OLD",
    "CustomerBotOpsTransitionError",
    "arm_customer_bot_transport",
    "disarm_customer_bot_transport",
    "intent_ops_cancel_reason",
    "load_customer_bot_ops",
    "ops_status",
    "ops_transport_may_run",
    "refresh_ops_start_cutoff",
    "resolve_ops_mode",
    "set_customer_bot_ops_mode",
]
