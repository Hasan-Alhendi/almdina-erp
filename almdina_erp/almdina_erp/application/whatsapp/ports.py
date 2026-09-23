from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol, Sequence


@dataclass(frozen=True, slots=True)
class WhatsAppSession:
    id: str
    name: str
    status: str
    phone: str | None = None
    push_name: str | None = None
    last_error: str | None = None
    engine_loaded: bool = False


@dataclass(frozen=True, slots=True)
class QrCode:
    qr_code: str
    status: str


@dataclass(frozen=True, slots=True)
class MessageReceipt:
    message_id: str
    timestamp: int = 0


@dataclass(frozen=True, slots=True)
class SendTextResult:
    ok: bool
    code: str
    message: str
    order_name: str
    chat_id: str = ""
    text_message_id: str = ""


@dataclass(frozen=True, slots=True)
class SendMeasurementsResult:
    ok: bool
    code: str
    message: str
    order_name: str
    chat_id: str = ""
    text_sent: bool = False
    document_sent: bool = False
    text_message_id: str = ""
    document_message_id: str = ""


class WhatsAppGateway(Protocol):
    def list_sessions(self) -> Sequence[WhatsAppSession]: ...

    def create_session(self, name: str) -> WhatsAppSession: ...

    def get_session(self, session_id: str) -> WhatsAppSession: ...

    def start(self, session_id: str) -> WhatsAppSession: ...

    def stop(self, session_id: str) -> WhatsAppSession: ...

    def get_qr(self, session_id: str) -> QrCode: ...

    def send_text(self, session_id: str, chat_id: str, text: str) -> MessageReceipt: ...

    def send_document(
        self,
        session_id: str,
        chat_id: str,
        *,
        filename: str,
        mimetype: str,
        data: bytes,
    ) -> MessageReceipt: ...


class MeasurementPdfGateway(Protocol):
    def render_measurements_pdf(self, order_name: str) -> bytes: ...


class InvoicePdfGateway(Protocol):
    def render_invoice_pdf(
        self,
        order_name: str,
        invoice_payload: Mapping[str, Any] | None = None,
    ) -> bytes: ...


class CustomerPhoneGateway(Protocol):
    def get_customer_phone(self, order_name: str) -> str: ...


__all__ = [
    "CustomerPhoneGateway",
    "InvoicePdfGateway",
    "MeasurementPdfGateway",
    "MessageReceipt",
    "QrCode",
    "SendMeasurementsResult",
    "SendTextResult",
    "WhatsAppGateway",
    "WhatsAppSession",
]
