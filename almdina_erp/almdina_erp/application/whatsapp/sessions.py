from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from almdina_erp.almdina_erp.domain.whatsapp.session_policy import (
    FACTORY_SESSION_NAME,
    is_working,
    needs_qr,
    select_factory_session,
    should_create_session,
)

from .errors import WhatsAppError, WhatsAppTransportError
from .ports import WhatsAppGateway, WhatsAppSession


def _as_mapping(session: WhatsAppSession) -> dict[str, object]:
    return {
        "id": session.id,
        "name": session.name,
        "status": session.status,
        "phone": session.phone,
        "push_name": session.push_name,
        "last_error": session.last_error,
        "engine_loaded": session.engine_loaded,
    }


def session_snapshot(session: WhatsAppSession | None, *, configured: bool = True) -> dict[str, Any]:
    if not configured:
        return {
            "configured": False,
            "session": None,
            "working": False,
            "can_create": False,
            "needs_reconnect": False,
            "needs_qr": False,
            "code": "not_configured",
            "reason": "لم يتم ضبط عنوان خادم WhatsApp أو مفتاح API.",
        }
    if session is None:
        return {
            "configured": True,
            "session": None,
            "working": False,
            "can_create": True,
            "needs_reconnect": False,
            "needs_qr": False,
            "code": "missing_session",
            "reason": "لا توجد جلسة WhatsApp مرتبطة.",
        }
    working = is_working(session.status)
    return {
        "configured": True,
        "session": _as_mapping(session),
        "working": working,
        "can_create": False,
        "needs_reconnect": not working,
        "needs_qr": needs_qr(session.status),
        "code": "ready" if working else "not_ready",
        "reason": "" if working else (session.last_error or "جلسة WhatsApp غير متصلة."),
    }


def get_factory_session(gateway: WhatsAppGateway) -> WhatsAppSession | None:
    selected = select_factory_session(
        [_as_mapping(session) for session in gateway.list_sessions()]
    )
    if selected is None:
        return None
    session_id = str(selected.get("id") or "").strip()
    if not session_id:
        return None
    return gateway.get_session(session_id)


def create_and_start_factory_session(gateway: WhatsAppGateway) -> WhatsAppSession:
    decision = should_create_session(
        [_as_mapping(session) for session in gateway.list_sessions()]
    )
    if not decision.allowed:
        raise WhatsAppError(decision.code, decision.reason)
    created = gateway.create_session(FACTORY_SESSION_NAME)
    return _start_if_needed(gateway, created)


def reconnect_factory_session(gateway: WhatsAppGateway) -> WhatsAppSession:
    session = get_factory_session(gateway)
    if session is None:
        raise WhatsAppError("missing_session", "لا توجد جلسة WhatsApp مرتبطة.")
    if is_working(session.status):
        return session
    return _start_if_needed(gateway, session)


def stop_factory_session(gateway: WhatsAppGateway) -> WhatsAppSession:
    session = get_factory_session(gateway)
    if session is None:
        raise WhatsAppError("missing_session", "لا توجد جلسة WhatsApp مرتبطة.")
    if not session.engine_loaded:
        return session
    return gateway.stop(session.id)


def get_session_qr(gateway: WhatsAppGateway) -> dict[str, Any]:
    session = get_factory_session(gateway)
    if session is None:
        raise WhatsAppError("missing_session", "لا توجد جلسة WhatsApp مرتبطة.")
    if is_working(session.status):
        return {
            "qr_code": "",
            "status": session.status,
            "working": True,
            "session": session_snapshot(session)["session"],
        }
    try:
        qr = gateway.get_qr(session.id)
    except WhatsAppTransportError as error:
        refreshed = gateway.get_session(session.id)
        if is_working(refreshed.status):
            return {
                "qr_code": "",
                "status": refreshed.status,
                "working": True,
                "session": session_snapshot(refreshed)["session"],
            }
        raise WhatsAppError("qr_unavailable", str(error) or "تعذر جلب رمز QR.") from error
    return {
        "qr_code": qr.qr_code,
        "status": qr.status,
        "working": is_working(qr.status),
        "session": session_snapshot(
            WhatsAppSession(
                id=session.id,
                name=session.name,
                status=qr.status or session.status,
                phone=session.phone,
                push_name=session.push_name,
                last_error=session.last_error,
                engine_loaded=session.engine_loaded,
            )
        )["session"],
    }


def _start_if_needed(gateway: WhatsAppGateway, session: WhatsAppSession) -> WhatsAppSession:
    if session.engine_loaded or is_working(session.status):
        return session
    try:
        return gateway.start(session.id)
    except WhatsAppTransportError as error:
        raise WhatsAppError(
            "start_failed",
            str(error) or "تعذر بدء جلسة WhatsApp.",
        ) from error


def delivery_status(gateway: WhatsAppGateway) -> Mapping[str, Any]:
    snapshot = session_snapshot(get_factory_session(gateway))
    return {
        "configured": True,
        "working": bool(snapshot["working"]),
        "code": snapshot["code"],
        "reason": snapshot["reason"],
    }


__all__ = [
    "create_and_start_factory_session",
    "delivery_status",
    "get_factory_session",
    "get_session_qr",
    "reconnect_factory_session",
    "session_snapshot",
    "stop_factory_session",
]
