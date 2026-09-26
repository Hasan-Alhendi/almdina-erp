from __future__ import annotations

import secrets
from collections.abc import Mapping
from typing import Any

from almdina_erp.almdina_erp.domain.whatsapp.session_policy import (
    SessionNameError,
    is_working,
    needs_qr,
    sessions_named,
    unique_session_name,
)

from .errors import WhatsAppError, WhatsAppTransportError
from .ports import WhatsAppGateway, WhatsAppSession, WhatsAppSessionStore


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
        "needs_qr": not working,
        "code": "ready" if working else "not_ready",
        "reason": "" if working else (session.last_error or "جلسة WhatsApp غير متصلة."),
    }


def get_factory_session(
    gateway: WhatsAppGateway,
    store: WhatsAppSessionStore,
) -> WhatsAppSession | None:
    session = _load_bound_session(gateway, store)
    if session is not None:
        return session
    return _reclaim_saved_session(gateway, store)


def create_and_start_factory_session(
    gateway: WhatsAppGateway,
    store: WhatsAppSessionStore,
) -> WhatsAppSession:
    existing = get_factory_session(gateway, store)
    if existing is not None:
        return _start_for_pairing(gateway, existing)
    try:
        name = unique_session_name(
            [session.name for session in gateway.list_sessions()],
            _draw_session_token,
        )
    except SessionNameError as error:
        raise WhatsAppError(error.code, str(error)) from error
    store.save_session_name(name)
    try:
        created = gateway.create_session(name)
    except WhatsAppTransportError as error:
        try:
            existing = _reclaim_saved_session(gateway, store)
        except WhatsAppTransportError:
            raise error
        if existing is None:
            raise error
        return _start_for_pairing(gateway, existing)
    session_id = str(created.id or "").strip()
    if not session_id:
        raise WhatsAppError("missing_session", "تعذر حفظ معرّف جلسة WhatsApp.")
    store.save_session_id(session_id)
    if str(created.name or "").strip():
        store.save_session_name(created.name)
    return _start_for_pairing(gateway, created)


def reconnect_factory_session(
    gateway: WhatsAppGateway,
    store: WhatsAppSessionStore,
) -> WhatsAppSession:
    session = get_factory_session(gateway, store)
    if session is None:
        raise WhatsAppError("missing_session", "لا توجد جلسة WhatsApp مرتبطة.")
    return _start_for_pairing(gateway, session)


def stop_factory_session(
    gateway: WhatsAppGateway,
    store: WhatsAppSessionStore,
) -> WhatsAppSession:
    session = get_factory_session(gateway, store)
    if session is None:
        raise WhatsAppError("missing_session", "لا توجد جلسة WhatsApp مرتبطة.")
    if not session.engine_loaded:
        return session
    return gateway.stop(session.id)


def get_session_qr(
    gateway: WhatsAppGateway,
    store: WhatsAppSessionStore,
) -> dict[str, Any]:
    session = get_factory_session(gateway, store)
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


def _start_for_pairing(gateway: WhatsAppGateway, session: WhatsAppSession) -> WhatsAppSession:
    """Start a non-working session, then leave it available for a QR request."""

    if is_working(session.status):
        return session
    if session.engine_loaded and needs_qr(session.status):
        return session
    try:
        return gateway.start(session.id)
    except WhatsAppTransportError:
        try:
            return gateway.get_session(session.id)
        except WhatsAppTransportError:
            return session


def _draw_session_token() -> str:
    return secrets.token_hex(4)


def _reclaim_saved_session(
    gateway: WhatsAppGateway,
    store: WhatsAppSessionStore,
) -> WhatsAppSession | None:
    """Bind this site to the session whose saved name it already owns."""

    saved_name = str(store.get_session_name() or "").strip()
    if not saved_name:
        return None
    matches = sessions_named(
        [_as_mapping(session) for session in gateway.list_sessions()],
        saved_name,
    )
    if len(matches) > 1:
        raise WhatsAppError(
            "ambiguous_session",
            "يوجد أكثر من جلسة WhatsApp بالاسم نفسه. لم يتم اختيار أي منها.",
        )
    if not matches:
        return None
    session_id = str(matches[0].get("id") or "").strip()
    if not session_id:
        return None
    session = gateway.get_session(session_id)
    store.save_session_id(session.id)
    return session


def _load_bound_session(
    gateway: WhatsAppGateway,
    store: WhatsAppSessionStore,
) -> WhatsAppSession | None:
    session_id = str(store.get_session_id() or "").strip()
    if not session_id:
        return None
    try:
        return gateway.get_session(session_id)
    except WhatsAppTransportError as error:
        if error.status_code == 404:
            return None
        raise


def delivery_status(
    gateway: WhatsAppGateway,
    store: WhatsAppSessionStore,
) -> Mapping[str, Any]:
    snapshot = session_snapshot(get_factory_session(gateway, store))
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
