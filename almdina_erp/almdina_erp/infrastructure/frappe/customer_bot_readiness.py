"""Read-only customer-bot production readiness check (no secrets, no sends).

Does not create inbound events, reply intents, or WhatsApp messages. Optional
network probes are GET-only with a short timeout.
"""

from __future__ import annotations

from typing import Any

from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_ops import (
    load_customer_bot_ops,
    ops_transport_may_run,
)
from almdina_erp.almdina_erp.infrastructure.whatsapp.customer_bot_ops_config import (
    OPS_MODE_PRODUCTION,
)


_NETWORK_TIMEOUT_SEC = 3.0
_DELIVERY_TICK = (
    "almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_reply_delivery"
    ".scheduled_customer_bot_reply_tick"
)


def check_customer_bot_readiness(*, probe_network: bool = False) -> dict[str, Any]:
    """Return an operator-safe readiness snapshot.

    ``probe_network`` may perform a timed GET against the OpenWA session status
    endpoint. It never starts, stops, or logs out a session and never registers
    a webhook.
    """

    import frappe

    ops = load_customer_bot_ops()
    lab = _lab_switch()
    connection = _connection_snapshot()
    factory_session_id = _factory_session_id()
    session_match = bool(
        connection["session_id"]
        and factory_session_id
        and connection["session_id"] == factory_session_id
    )
    published = _published_texts_ok()
    scheduler = _scheduler_snapshot()
    workers = _worker_indicators()
    pdf = _pdf_engine_snapshot()
    network: dict[str, Any] = {"probed": False}
    if probe_network and connection["session_id"] and connection["openwa_configured"]:
        network = _probe_session_status(connection["session_id"])

    checks = {
        "ops_mode_set": ops.mode in {"off", "pilot", "production"},
        "ops_ready": ops.is_ready,
        "lab_enabled": lab["enabled"],
        "lab_accepting": lab["accepting_messages"],
        "transport_armed": ops.transport_armed,
        "transport_live": ops.transport_live,
        "transport_may_run": ops_transport_may_run(live_module_enabled=False),
        "inbound_connection_complete": connection["complete"],
        "webhook_secret_configured": connection["webhook_secret_configured"],
        "openwa_env_configured": connection["openwa_configured"],
        "factory_session_id_present": bool(factory_session_id),
        "bot_session_matches_factory": session_match,
        "published_texts_valid": published,
        "scheduler_enabled": scheduler["enable_scheduler"],
        "delivery_tick_registered": scheduler["delivery_tick_registered"],
        "worker_processes_seen": workers["process_count"] > 0,
        "pdf_engine_available": pdf["available"],
    }
    blockers = [name for name, ok in checks.items() if not ok]
    # Soft indicators: workers and network are informative, not hard blockers
    # for a stopped staging check.
    soft = {"worker_processes_seen", "transport_may_run", "transport_armed", "transport_live"}
    if ops.mode != OPS_MODE_PRODUCTION:
        soft |= {
            "ops_ready",
            "lab_enabled",
            "lab_accepting",
            "bot_session_matches_factory",
        }
    hard_blockers = [name for name in blockers if name not in soft]

    return {
        "ok": len(hard_blockers) == 0,
        "ops": {
            "mode": ops.mode,
            "is_ready": ops.is_ready,
            "pilot_phone_e164": ops.pilot_phone_e164,
            "started_at": (
                ops.started_at.isoformat().replace("+00:00", "Z") if ops.started_at else None
            ),
            "transport_armed": ops.transport_armed,
            "transport_live": ops.transport_live,
            "transport_may_run": checks["transport_may_run"],
        },
        "lab": lab,
        "connection": {
            "connection_ref_set": bool(connection["connection_ref"]),
            "session_id_set": bool(connection["session_id"]),
            "session_id_matches_factory": session_match,
            "factory_session_id_set": bool(factory_session_id),
            "webhook_secret_configured": connection["webhook_secret_configured"],
            "openwa_env_configured": connection["openwa_configured"],
            # Never return the actual session id in full if it looks like a secret;
            # operators already know it — show only whether values match.
            "bot_session_fingerprint": _fingerprint(connection["session_id"]),
            "factory_session_fingerprint": _fingerprint(factory_session_id),
        },
        "published_texts_valid": published,
        "scheduler": scheduler,
        "workers": workers,
        "pdf": pdf,
        "network": network,
        "checks": checks,
        "hard_blockers": hard_blockers,
        "notes": [
            "Presence of a worker process does not guarantee the delivery job runs.",
            "accepted means the gateway accepted the send request, not customer receipt.",
            "This check creates no events, intents, or WhatsApp messages.",
            "LIVE_REPLY_DELIVERY_ENABLED stays False; use transport_armed or transport_live.",
        ],
        "site": getattr(frappe.local, "site", None),
    }


def _lab_switch() -> dict[str, Any]:
    from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_settings_repository import (
        load_customer_bot_runtime,
    )

    try:
        runtime = load_customer_bot_runtime()
    except Exception:
        return {
            "enabled": False,
            "accepting_messages": False,
            "acceptance_epoch": 0,
            "revision": 0,
        }
    return {
        "enabled": runtime.enabled,
        "accepting_messages": runtime.accepting_messages,
        "acceptance_epoch": runtime.acceptance_epoch,
        "revision": runtime.revision,
    }


def _connection_snapshot() -> dict[str, Any]:
    from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_inbound_connection import (
        load_openwa_inbound_connection,
    )
    from almdina_erp.almdina_erp.infrastructure.whatsapp.config import load_openwa_config

    config = load_openwa_inbound_connection()
    openwa = load_openwa_config()
    if config is None:
        return {
            "complete": False,
            "connection_ref": "",
            "session_id": "",
            "webhook_secret_configured": False,
            "openwa_configured": openwa.configured,
        }
    return {
        "complete": True,
        "connection_ref": config.connection_ref,
        "session_id": config.session_id,
        "webhook_secret_configured": bool(config.webhook_secret),
        "openwa_configured": openwa.configured,
    }


def _factory_session_id() -> str:
    try:
        from almdina_erp.almdina_erp.infrastructure.whatsapp.session_store import (
            FrappeWhatsAppSessionStore,
        )

        return str(FrappeWhatsAppSessionStore().get_session_id() or "").strip()
    except Exception:
        return ""


def _published_texts_ok() -> bool:
    from almdina_erp.almdina_erp.domain.customer_bot.message_templates import validate_texts
    from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_settings_repository import (
        FrappeCustomerBotSettingsRepository,
    )

    try:
        snapshot = FrappeCustomerBotSettingsRepository().load()
    except Exception:
        return False
    return not validate_texts(snapshot.published)


def _scheduler_snapshot() -> dict[str, Any]:
    import frappe

    enable_scheduler = False
    try:
        enable_scheduler = bool(frappe.db.get_single_value("System Settings", "enable_scheduler"))
    except Exception:
        enable_scheduler = False
    registered = False
    try:
        from almdina_erp import hooks

        cron = getattr(hooks, "scheduler_events", {}).get("cron", {})
        for jobs in cron.values():
            if _DELIVERY_TICK in jobs:
                registered = True
                break
    except Exception:
        registered = False
    return {
        "enable_scheduler": enable_scheduler,
        "delivery_tick_registered": registered,
        "delivery_tick": _DELIVERY_TICK,
    }


def _worker_indicators() -> dict[str, Any]:
    """Best-effort process count. Not proof that RQ will execute the job."""

    count = 0
    try:
        import os
        import subprocess

        site = os.environ.get("FRAPPE_SITE") or ""
        # Match common bench worker process names without reading job payloads.
        result = subprocess.run(
            ["pgrep", "-af", "frappe.*worker|bench worker"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        lines = [line for line in (result.stdout or "").splitlines() if line.strip()]
        count = len(lines)
        return {
            "process_count": count,
            "site_hint": site or None,
            "note": "process presence is not a guarantee of job execution",
        }
    except Exception as error:
        return {
            "process_count": count,
            "error": type(error).__name__,
            "note": "process presence is not a guarantee of job execution",
        }


def _pdf_engine_snapshot() -> dict[str, Any]:
    try:
        from frappe.utils.print_utils import find_or_download_chromium_executable

        executable = str(find_or_download_chromium_executable() or "").strip()
        return {"available": bool(executable), "engine": "chromium" if executable else None}
    except Exception as error:
        return {"available": False, "engine": None, "error": type(error).__name__}


def _probe_session_status(session_id: str) -> dict[str, Any]:
    """Timed read-only GET. Never mutates the session."""

    try:
        from almdina_erp.almdina_erp.infrastructure.whatsapp.config import load_openwa_config

        config = load_openwa_config()
        if not config.configured:
            return {"probed": False, "reason": "openwa_not_configured"}
        import json
        import urllib.error
        import urllib.request

        url = f"{config.base_url.rstrip('/')}/api/sessions/{session_id}"
        request = urllib.request.Request(
            url,
            headers={"X-API-Key": config.api_key, "Accept": "application/json"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=_NETWORK_TIMEOUT_SEC) as response:
                body = response.read(4096)
                status = response.status
        except urllib.error.HTTPError as error:
            return {
                "probed": True,
                "http_status": int(error.code),
                "reachable": True,
                "session_ready": False,
            }
        except Exception as error:
            return {
                "probed": True,
                "reachable": False,
                "error": type(error).__name__,
            }
        ready = False
        try:
            payload = json.loads(body.decode("utf-8"))
            status_text = str(payload.get("status") or payload.get("state") or "").lower()
            ready = status_text in {"ready", "working", "authenticated", "connected"}
        except Exception:
            payload = None
        return {
            "probed": True,
            "reachable": True,
            "http_status": status,
            "session_ready": ready,
        }
    except Exception as error:
        return {"probed": True, "reachable": False, "error": type(error).__name__}


def _fingerprint(value: str) -> str | None:
    if not value:
        return None
    import hashlib

    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


__all__ = ["check_customer_bot_readiness"]
