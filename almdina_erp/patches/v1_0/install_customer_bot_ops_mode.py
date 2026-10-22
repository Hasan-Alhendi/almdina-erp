"""Record an explicit customer-bot ops mode without enabling production.

Idempotent: writes ``customer_bot_ops_mode`` only when the key is absent.

- Legacy pilot sites (``customer_bot_pilot_enabled`` truthy) → ``pilot``.
- All other sites → ``off``.

Never writes ``production``. Does not change transport arm flags, pilot phone,
start stamps, Customer Bot Settings texts, or lab ``enabled``.
"""

from __future__ import annotations


def execute() -> None:
    import frappe
    from frappe.installer import update_site_config

    conf = frappe.get_site_config() or {}
    if "customer_bot_ops_mode" in conf:
        return

    raw = conf.get("customer_bot_pilot_enabled")
    pilot_on = False
    if raw is True or raw == 1:
        pilot_on = True
    elif isinstance(raw, str) and raw.strip().lower() in {"1", "true", "yes", "on"}:
        pilot_on = True

    mode = "pilot" if pilot_on else "off"
    update_site_config("customer_bot_ops_mode", mode)


__all__ = ["execute"]
