from __future__ import annotations

from collections.abc import Mapping

from almdina_erp.almdina_erp.domain.whatsapp.message_templates import (
    INVOICE_TEXT_TEMPLATE,
    format_whatsapp_preamble,
)
from almdina_erp.almdina_erp.domain.whatsapp.phone import (
    PhoneNormalizationError,
    normalize_syrian_whatsapp_chat_id,
)
from almdina_erp.almdina_erp.domain.whatsapp.session_policy import is_working

from .errors import WhatsAppError, WhatsAppTransportError
from .ports import (
    CustomerPhoneGateway,
    InvoicePdfGateway,
    SendMeasurementsResult,
    WhatsAppGateway,
)
from .send_measurements import MEASUREMENTS_PDF_MIMETYPE
from .sessions import get_factory_session


def invoice_filename(order_name: str) -> str:
    safe = "".join(
        character if character.isalnum() or character in "-_" else "_"
        for character in str(order_name or "").strip()
    ) or "order"
    return f"فاتورة-{safe}.pdf"


def send_order_invoice(
    gateway: WhatsAppGateway,
    pdf_gateway: InvoicePdfGateway,
    phone_gateway: CustomerPhoneGateway,
    order_name: object,
    invoice_payload: Mapping[str, object] | None = None,
    text_template: object = None,
) -> SendMeasurementsResult:
    name = str(order_name or "").strip()
    if not name:
        raise WhatsAppError("missing_order", "تعذر تحديد الطلب لإرسال الفاتورة.")

    session = get_factory_session(gateway)
    if session is None:
        raise WhatsAppError("missing_session", "لا توجد جلسة WhatsApp مرتبطة.")
    if not is_working(session.status):
        raise WhatsAppError(
            "session_not_ready",
            "جلسة WhatsApp غير متصلة. لن يتم إرسال الرسالة.",
        )

    try:
        chat_id = normalize_syrian_whatsapp_chat_id(phone_gateway.get_customer_phone(name))
    except PhoneNormalizationError as error:
        raise WhatsAppError(error.code, str(error)) from error

    pdf = pdf_gateway.render_invoice_pdf(name, invoice_payload)
    if not pdf:
        raise WhatsAppError("pdf_failed", "تعذر إنشاء ملف PDF لفاتورة الزبون.")

    text = format_whatsapp_preamble(text_template, name, INVOICE_TEXT_TEMPLATE)
    try:
        text_receipt = gateway.send_text(session.id, chat_id, text)
    except WhatsAppTransportError as error:
        raise WhatsAppError(
            "text_failed",
            str(error) or "تعذر إرسال رسالة واتساب النصية.",
        ) from error

    try:
        document_receipt = gateway.send_document(
            session.id,
            chat_id,
            filename=invoice_filename(name),
            mimetype=MEASUREMENTS_PDF_MIMETYPE,
            data=pdf,
        )
    except WhatsAppTransportError as error:
        return SendMeasurementsResult(
            ok=False,
            code="document_failed",
            message=str(error) or "تم إرسال الرسالة النصية وتعذر إرسال ملف الفاتورة.",
            order_name=name,
            chat_id=chat_id,
            text_sent=True,
            document_sent=False,
            text_message_id=text_receipt.message_id,
        )

    return SendMeasurementsResult(
        ok=True,
        code="sent",
        message="تم إرسال فاتورة الزبون إلى الزبون عبر واتساب.",
        order_name=name,
        chat_id=chat_id,
        text_sent=True,
        document_sent=True,
        text_message_id=text_receipt.message_id,
        document_message_id=document_receipt.message_id,
    )


__all__ = [
    "invoice_filename",
    "send_order_invoice",
]
