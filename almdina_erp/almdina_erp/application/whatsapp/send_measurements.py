from __future__ import annotations

from almdina_erp.almdina_erp.domain.whatsapp.phone import (
    PhoneNormalizationError,
    normalize_syrian_whatsapp_chat_id,
)
from almdina_erp.almdina_erp.domain.whatsapp.message_templates import (
    MEASUREMENTS_TEXT_TEMPLATE,
    format_whatsapp_preamble,
)
from almdina_erp.almdina_erp.domain.whatsapp.session_policy import is_working

from .errors import WhatsAppError, WhatsAppTransportError
from .ports import (
    CustomerPhoneGateway,
    MeasurementPdfGateway,
    SendMeasurementsResult,
    WhatsAppGateway,
)
from .sessions import get_factory_session


MEASUREMENTS_PDF_MIMETYPE = "application/pdf"


def measurements_text(order_name: str, template: object = None) -> str:
    return format_whatsapp_preamble(template, order_name, MEASUREMENTS_TEXT_TEMPLATE)


def measurements_filename(order_name: str) -> str:
    safe = "".join(
        character if character.isalnum() or character in "-_" else "_"
        for character in str(order_name or "").strip()
    ) or "order"
    return f"قياسات-{safe}.pdf"


def send_order_measurements(
    gateway: WhatsAppGateway,
    pdf_gateway: MeasurementPdfGateway,
    phone_gateway: CustomerPhoneGateway,
    order_name: object,
    text_template: object = None,
) -> SendMeasurementsResult:
    name = str(order_name or "").strip()
    if not name:
        raise WhatsAppError("missing_order", "تعذر تحديد الطلب لإرسال القياسات.")

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

    pdf = pdf_gateway.render_measurements_pdf(name)
    if not pdf:
        raise WhatsAppError("pdf_failed", "تعذر إنشاء ملف PDF لجدول القياسات.")

    text = measurements_text(name, text_template)
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
            filename=measurements_filename(name),
            mimetype=MEASUREMENTS_PDF_MIMETYPE,
            data=pdf,
        )
    except WhatsAppTransportError as error:
        return SendMeasurementsResult(
            ok=False,
            code="document_failed",
            message=str(error) or "تم إرسال الرسالة النصية وتعذر إرسال ملف القياسات.",
            order_name=name,
            chat_id=chat_id,
            text_sent=True,
            document_sent=False,
            text_message_id=text_receipt.message_id,
        )

    return SendMeasurementsResult(
        ok=True,
        code="sent",
        message="تم إرسال جدول القياسات إلى الزبون عبر واتساب.",
        order_name=name,
        chat_id=chat_id,
        text_sent=True,
        document_sent=True,
        text_message_id=text_receipt.message_id,
        document_message_id=document_receipt.message_id,
    )


__all__ = [
    "MEASUREMENTS_PDF_MIMETYPE",
    "MEASUREMENTS_TEXT_TEMPLATE",
    "measurements_filename",
    "measurements_text",
    "send_order_measurements",
]
