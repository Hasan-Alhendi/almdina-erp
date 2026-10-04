from __future__ import annotations

from almdina_erp.almdina_erp.domain.whatsapp.message_templates import (
    STAGE_COMPLETION_TEXT_TEMPLATE,
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
    SendTextResult,
    WhatsAppGateway,
    WhatsAppSessionStore,
)
from .sessions import get_factory_session


def stage_completion_text(
    order_name: object,
    stage_label: object,
    template: object = None,
) -> str:
    return format_whatsapp_preamble(
        template,
        order_name,
        STAGE_COMPLETION_TEXT_TEMPLATE,
        stage_label=stage_label,
    )


def send_stage_completion(
    gateway: WhatsAppGateway,
    phone_gateway: CustomerPhoneGateway,
    order_name: object,
    stage_label: object,
    text_template: object = None,
    *,
    session_store: WhatsAppSessionStore,
) -> SendTextResult:
    name = str(order_name or "").strip()
    label = str(stage_label or "").strip()
    if not name:
        raise WhatsAppError("missing_order", "تعذر تحديد الطلب لإرسال رسالة المرحلة.")

    session = get_factory_session(gateway, session_store)
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

    text = stage_completion_text(name, label, text_template)
    try:
        receipt = gateway.send_text(session.id, chat_id, text)
    except WhatsAppTransportError as error:
        raise WhatsAppError(
            "text_failed",
            str(error) or "تعذر إرسال رسالة واتساب النصية.",
        ) from error

    return SendTextResult(
        ok=True,
        code="sent",
        message="تم إرسال رسالة إتمام المرحلة إلى الزبون عبر واتساب.",
        order_name=name,
        chat_id=chat_id,
        text_message_id=receipt.message_id,
    )


__all__ = [
    "STAGE_COMPLETION_TEXT_TEMPLATE",
    "send_stage_completion",
    "stage_completion_text",
]
