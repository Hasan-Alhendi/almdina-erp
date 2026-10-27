"""Customer-bot operation endpoints for a later UI.

Every call checks ``manage_customer_bot_operation``. The client cannot supply
a callback URL, a session id, or a secret. These methods do not log credentials.
"""

from __future__ import annotations

from typing import Any

import frappe

from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe.authorization_gateway import (
    require_doctype_capability,
)
from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_operation_runtime import (
    run_check,
    run_start,
    run_status,
    run_stop,
)


@frappe.whitelist(methods=["POST"])
def start_customer_bot_operation() -> dict[str, Any]:
    _authorize()
    return _safe(run_start)


@frappe.whitelist(methods=["POST"])
def stop_customer_bot_operation() -> dict[str, Any]:
    _authorize()
    return _safe(run_stop)


@frappe.whitelist(methods=["GET", "POST"])
def get_customer_bot_operation_status() -> dict[str, Any]:
    """Read the operation snapshot.

    Desk polling uses ``frappe.call``, which always POSTs. The extra verb does
    not add a write: this method only loads the saved snapshot.
    """

    _authorize()
    return _safe(run_status)


@frappe.whitelist(methods=["POST"])
def check_customer_bot_operation() -> dict[str, Any]:
    _authorize()
    return _safe(run_check)


def _authorize() -> None:
    require_doctype_capability(Capability.MANAGE_CUSTOMER_BOT_OPERATION)


def _safe(fn) -> dict[str, Any]:
    try:
        payload = fn()
    except Exception:
        frappe.log_error(title="customer bot operation failed", message="operation_failed")
        return {
            "decision": "stopped",
            "state": "needs_setup",
            "reason": "operation_failed",
            "sending_accepted": False,
            "customer_receipt_proven": False,
        }
    return _redact(payload)


def _redact(payload: dict[str, Any]) -> dict[str, Any]:
    hidden = {"secret", "api_key", "api_secret", "authorization", "token", "webhook_secret"}
    return {key: value for key, value in payload.items() if key not in hidden}


__all__ = [
    "check_customer_bot_operation",
    "get_customer_bot_operation_status",
    "start_customer_bot_operation",
    "stop_customer_bot_operation",
]
