"""Authenticated OpenWA webhook entry for the customer bot.

Login alone is not enough: the caller needs ``ingest_customer_bot_inbound``.
The HMAC signature is checked against the original body bytes before any bot
rows change. ``connection_ref`` comes from server settings, never from the body.
This endpoint does not send replies and does not use ``allow_guest``.
"""

from __future__ import annotations

from typing import Any

import frappe
from frappe import _

from almdina_erp.almdina_erp.domain.customer_bot.session_admission import (
    disposition_retries_later,
)
from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe.authorization_gateway import (
    require_doctype_capability,
)
from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_inbound_connection import (
    load_openwa_inbound_connection,
)
from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_inbound_gateway import (
    accept_verified_customer_bot_inbound,
)
from almdina_erp.almdina_erp.infrastructure.whatsapp.customer_bot_openwa_inbound import (
    OPENWA_MESSAGE_RECEIVED,
    OpenWAInboundError,
    map_openwa_message_received,
    parse_openwa_envelope,
    verify_openwa_signature,
)

_SIGNATURE_HEADER = "X-OpenWA-Signature"
_TRANSIENT_DB_MARKERS = (
    "Deadlock",
    "Lock wait timeout",
    "try restarting transaction",
    "WSREP",
    "Connection reset",
    "server has gone away",
    "Lost connection",
)


@frappe.whitelist(methods=["POST"])
def receive_openwa_customer_bot_event() -> dict[str, Any]:
    """Accept one signed OpenWA delivery for the configured customer-bot connection."""

    _authorize()
    config = load_openwa_inbound_connection()
    if config is None:
        return _fail(503, "connection_not_configured")

    raw_body = _raw_body()
    signature = _header(_SIGNATURE_HEADER)
    if not verify_openwa_signature(
        raw_body=raw_body,
        signature_header=signature,
        secret=config.webhook_secret,
    ):
        return _fail(403, "invalid_signature")

    try:
        envelope = parse_openwa_envelope(raw_body)
    except OpenWAInboundError as error:
        return _fail(400, error.code)

    session_id = envelope.get("sessionId")
    if not isinstance(session_id, str) or session_id.strip() != config.session_id:
        return _fail(403, "session_mismatch")

    event = envelope.get("event")
    delivery_id = envelope.get("deliveryId")
    delivery_token = delivery_id.strip() if isinstance(delivery_id, str) else ""

    if event != OPENWA_MESSAGE_RECEIVED:
        return _ok("ignored", delivery_id=delivery_token, provider_event_id="")

    try:
        message = map_openwa_message_received(envelope, connection_ref=config.connection_ref)
    except OpenWAInboundError as error:
        return _fail(400, error.code)
    except ValueError:
        return _fail(400, "invalid_message")

    try:
        acceptance = accept_verified_customer_bot_inbound(message)
    except Exception as error:
        if _is_transient_db_error(error):
            return _fail(503, "transient_persistence_error")
        raise

    if disposition_retries_later(acceptance.disposition):
        return _fail(503, acceptance.disposition, delivery_id=delivery_token)

    return _ok(
        acceptance.disposition,
        delivery_id=delivery_token,
        provider_event_id=message.provider_event_id,
    )


def _authorize() -> None:
    if frappe.session.user in {None, "", "Guest"}:
        frappe.throw(_("Authentication required."), frappe.PermissionError)
    require_doctype_capability(Capability.INGEST_CUSTOMER_BOT_INBOUND)


def _raw_body() -> bytes:
    request = getattr(frappe.local, "request", None)
    if request is None:
        return b""
    data = request.get_data(cache=True)
    if isinstance(data, memoryview):
        return data.tobytes()
    if isinstance(data, bytearray):
        return bytes(data)
    if isinstance(data, bytes):
        return data
    if isinstance(data, str):
        return data.encode("utf-8")
    return b""


def _header(name: str) -> str | None:
    request = getattr(frappe.local, "request", None)
    if request is None:
        return None
    value = request.headers.get(name)
    if value is None:
        return None
    return str(value)


def _ok(disposition: str, *, delivery_id: str, provider_event_id: str) -> dict[str, Any]:
    frappe.local.response["http_status_code"] = 200
    return {
        "ok": True,
        "disposition": disposition,
        "delivery_id": delivery_id,
        "provider_event_id": provider_event_id,
    }


def _fail(status: int, code: str, *, delivery_id: str = "") -> dict[str, Any]:
    frappe.local.response["http_status_code"] = status
    payload = {"ok": False, "code": code}
    if delivery_id:
        payload["delivery_id"] = delivery_id
    return payload


def _is_transient_db_error(error: BaseException) -> bool:
    text = f"{type(error).__name__}: {error}"
    return any(marker.lower() in text.lower() for marker in _TRANSIENT_DB_MARKERS)


__all__ = ["receive_openwa_customer_bot_event"]
