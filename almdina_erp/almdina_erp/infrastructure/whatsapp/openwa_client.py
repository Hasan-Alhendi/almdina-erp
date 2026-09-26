from __future__ import annotations

import base64
import json
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from almdina_erp.almdina_erp.application.whatsapp.errors import WhatsAppTransportError
from almdina_erp.almdina_erp.application.whatsapp.ports import (
    MessageReceipt,
    QrCode,
    WhatsAppSession,
)
from almdina_erp.almdina_erp.infrastructure.whatsapp.config import OpenWAConfig


_Opener = Callable[..., Any]
SESSION_SETUP_TIMEOUT_SEC = 180.0


class OpenWAClient:
    """HTTP adapter for the local OpenWA WhatsApp Web gateway."""

    def __init__(
        self,
        config: OpenWAConfig,
        *,
        opener: _Opener | None = None,
        timeout: float = 45,
    ) -> None:
        if not config.configured:
            raise WhatsAppTransportError(
                "لم يتم ضبط عنوان خادم WhatsApp أو مفتاح API.",
                code="not_configured",
            )
        self._config = config
        self._opener = opener or urlopen
        self._timeout = timeout

    def list_sessions(self) -> list[WhatsAppSession]:
        payload = self._request("GET", "/api/sessions")
        rows = payload if isinstance(payload, list) else []
        return [_session(row) for row in rows if isinstance(row, dict)]

    def create_session(self, name: str) -> WhatsAppSession:
        return _session(
            self._request(
                "POST",
                "/api/sessions",
                {"name": name},
                timeout=SESSION_SETUP_TIMEOUT_SEC,
            )
        )

    def get_session(self, session_id: str) -> WhatsAppSession:
        return _session(self._request("GET", f"/api/sessions/{session_id}"))

    def start(self, session_id: str) -> WhatsAppSession:
        return _session(
            self._request(
                "POST",
                f"/api/sessions/{session_id}/start",
                timeout=SESSION_SETUP_TIMEOUT_SEC,
            )
        )

    def stop(self, session_id: str) -> WhatsAppSession:
        return _session(self._request("POST", f"/api/sessions/{session_id}/stop"))

    def get_qr(self, session_id: str) -> QrCode:
        payload = self._request("GET", f"/api/sessions/{session_id}/qr")
        data = payload if isinstance(payload, dict) else {}
        return QrCode(
            qr_code=str(data.get("qrCode") or ""),
            status=str(data.get("status") or ""),
        )

    def send_text(self, session_id: str, chat_id: str, text: str) -> MessageReceipt:
        payload = self._request(
            "POST",
            f"/api/sessions/{session_id}/messages/send-text",
            {"chatId": chat_id, "text": text},
        )
        return _receipt(payload)

    def send_document(
        self,
        session_id: str,
        chat_id: str,
        *,
        filename: str,
        mimetype: str,
        data: bytes,
        caption: str = "",
    ) -> MessageReceipt:
        body: dict[str, Any] = {
            "chatId": chat_id,
            "filename": filename,
            "mimetype": mimetype,
            "base64": base64.b64encode(data).decode("ascii"),
        }
        caption_text = str(caption or "").strip()
        if caption_text:
            body["caption"] = caption_text
        payload = self._request(
            "POST",
            f"/api/sessions/{session_id}/messages/send-document",
            body,
        )
        return _receipt(payload)

    def _request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> Any:
        encoded = None if body is None else json.dumps(body).encode("utf-8")
        headers = {
            "Accept": "application/json",
            "X-API-Key": self._config.api_key,
        }
        if encoded is not None:
            headers["Content-Type"] = "application/json"
        request = Request(
            f"{self._config.base_url}{path}",
            data=encoded,
            headers=headers,
            method=method,
        )
        try:
            with self._opener(
                request,
                timeout=self._timeout if timeout is None else timeout,
            ) as response:
                raw = response.read()
                if not raw:
                    return {}
                return json.loads(raw.decode("utf-8"))
        except HTTPError as error:
            try:
                detail = _error_detail(error)
                raise WhatsAppTransportError(
                    detail or f"OpenWA rejected {method} {path} ({error.code}).",
                    status_code=int(error.code),
                ) from error
            finally:
                error.close()
        except TimeoutError as error:
            raise WhatsAppTransportError(
                "انتهت مهلة الاتصال بخادم WhatsApp.",
                code="timeout",
            ) from error
        except URLError as error:
            reason = getattr(error, "reason", None)
            timed_out = isinstance(reason, TimeoutError) or "timed out" in str(reason or "").lower()
            raise WhatsAppTransportError(
                "انتهت مهلة الاتصال بخادم WhatsApp."
                if timed_out
                else "تعذر الاتصال بخادم WhatsApp المحلي.",
                code="timeout" if timed_out else "unreachable",
            ) from error
        except json.JSONDecodeError as error:
            raise WhatsAppTransportError(
                "رد خادم WhatsApp غير صالح.",
                code="invalid_response",
            ) from error


def _session(payload: Any) -> WhatsAppSession:
    data = payload if isinstance(payload, dict) else {}
    phone = data.get("phone")
    push_name = data.get("pushName")
    last_error = data.get("lastError")
    return WhatsAppSession(
        id=str(data.get("id") or ""),
        name=str(data.get("name") or ""),
        status=str(data.get("status") or ""),
        phone=None if phone in (None, "") else str(phone),
        push_name=None if push_name in (None, "") else str(push_name),
        last_error=None if last_error in (None, "") else str(last_error),
        engine_loaded=bool(data.get("engineLoaded")),
    )


def _receipt(payload: Any) -> MessageReceipt:
    data = payload if isinstance(payload, dict) else {}
    return MessageReceipt(
        message_id=str(data.get("messageId") or ""),
        timestamp=int(data.get("timestamp") or 0),
    )


def _error_detail(error: HTTPError) -> str:
    try:
        raw = error.read()
    except Exception:
        return str(error.reason or "")
    if not raw:
        return str(error.reason or "")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return raw.decode("utf-8", errors="replace")[:300]
    if isinstance(payload, dict):
        for key in ("message", "error", "detail"):
            value = payload.get(key)
            if value:
                return str(value)
    return str(error.reason or "")


__all__ = ["OpenWAClient", "SESSION_SETUP_TIMEOUT_SEC"]
