"""Installed Arabic wording for the customer bot.

These strings are content, not conversation rules. The engine still returns
message keys. A site can replace this copy from factory settings.
"""

from __future__ import annotations

from .conversation import BotMessageKey, BotService
from .message_templates import service_title_key, status_label_key
from .order_followup import PublicOrderStatus


def default_texts() -> dict[str, str]:
    return {
        BotMessageKey.WELCOME: "مرحباً بك، حدد ماذا تريد:",
        BotMessageKey.INVALID_MENU_CHOICE: "اختر 1 أو 2 أو 3 أو 4.",
        BotMessageKey.NO_CURRENT_ORDERS: "لا توجد طلبات غير مسلّمة. أدخل الرقم الكامل لطلب سابق إن أردت.",
        BotMessageKey.ASK_ORDER_NUMBER: "أدخل رقم الطلب الكامل، أو أرسل 0 للقائمة الرئيسية.",
        BotMessageKey.CURRENT_ORDER_LINE: "{order_name} {order_date} {public_status}",
        BotMessageKey.ORDER_NOT_FOUND: "لم يتم العثور على الطلب.",
        BotMessageKey.ORDER_NOT_CURRENT: "هذه النسخة ليست الطلب الحالي.",
        BotMessageKey.ORDER_CANCELLED: "هذا الطلب تم إلغاؤه سابقاً.",
        BotMessageKey.ORDER_STATUS: "{order_name}: {public_status}",
        BotMessageKey.UNREGISTERED_PHONE: "عذراً رقمك غير مسجل بالنظام، قم بالتواصل مع الموظف من فضلك",
        BotMessageKey.INVALID_ORDER_NUMBER: "أدخل رقم الطلب الكامل كما هو، أو أرسل {return_digit} للقائمة الرئيسية.",
        BotMessageKey.SERVICE_UNAVAILABLE: "هذه الخدمة غير متاحة حالياً.",
        service_title_key(BotService.ORDER_STATUS): "لمعرفة حالة طلب معين",
        service_title_key(BotService.FINAL_COST): "لمعرفة تكلفة طلب",
        service_title_key(BotService.APPROVED_CUTTING_PLAN): "لمعرفة خطة القص لطلب معين",
        service_title_key(BotService.MEASUREMENTS): "لعرض قياسات طلب معين",
        status_label_key(PublicOrderStatus.AWAITING_START): "بانتظار بدء العمل.",
        status_label_key(PublicOrderStatus.IN_PROGRESS): "جار العمل على الطلب.",
        status_label_key(PublicOrderStatus.READY_FOR_PICKUP): "جاهز للاستلام.",
        status_label_key(PublicOrderStatus.DELIVERED): "تم التسليم.",
        status_label_key(PublicOrderStatus.CANCELLED): "هذا الطلب تم إلغاؤه سابقاً.",
        status_label_key(PublicOrderStatus.UNSUPPORTED): "تعذر تحديد حالة الطلب حالياً، يرجى التواصل مع الموظف.",
    }


def variable_examples() -> dict[str, str]:
    texts = default_texts()
    return {
        "order_name": "DCO-2026-00021",
        "order_date": "2026-10-18",
        "public_status": texts[status_label_key(PublicOrderStatus.AWAITING_START)],
        "service_id": texts[service_title_key(BotService.ORDER_STATUS)],
        "return_digit": "0",
    }


__all__ = ["default_texts", "variable_examples"]
