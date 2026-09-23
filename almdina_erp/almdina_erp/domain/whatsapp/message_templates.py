from __future__ import annotations


MEASUREMENTS_TEXT_TEMPLATE = "نرفق لك جدول القياسات الخاص بطلبك رقم {order_name}"
INVOICE_TEXT_TEMPLATE = MEASUREMENTS_TEXT_TEMPLATE
STAGE_COMPLETION_TEXT_TEMPLATE = "طلبك رقم {order_name} اكتملت مرحلة {stage_label}"
ORDER_NAME_PLACEHOLDER = "{order_name}"
STAGE_LABEL_PLACEHOLDER = "{stage_label}"


def format_whatsapp_preamble(
    template: object,
    order_name: object,
    default: str = MEASUREMENTS_TEXT_TEMPLATE,
    *,
    stage_label: object = "",
) -> str:
    """Build customer WhatsApp copy.

    Only `{order_name}` and `{stage_label}` are substituted. Empty templates
    fall back to `default`. Extra braces in the stored copy are left unchanged.
    """

    name = str(order_name or "").strip()
    label = str(stage_label or "").strip()
    text = str(template or "").strip() or str(default or "").strip() or MEASUREMENTS_TEXT_TEMPLATE
    return text.replace(ORDER_NAME_PLACEHOLDER, name).replace(STAGE_LABEL_PLACEHOLDER, label)


__all__ = [
    "INVOICE_TEXT_TEMPLATE",
    "MEASUREMENTS_TEXT_TEMPLATE",
    "ORDER_NAME_PLACEHOLDER",
    "STAGE_COMPLETION_TEXT_TEMPLATE",
    "STAGE_LABEL_PLACEHOLDER",
    "format_whatsapp_preamble",
]
