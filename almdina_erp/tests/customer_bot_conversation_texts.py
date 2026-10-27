"""Arabic text used only to render conversation simulations in tests.

These sentences are not factory settings and are not loaded by the engine.
"""

from __future__ import annotations

STATUS_TEXT = {
    "awaiting_start": "بانتظار بدء العمل.",
    "in_progress": "جار العمل على الطلب.",
    "ready_for_pickup": "جاهز للاستلام.",
    "delivered": "تم التسليم.",
    "cancelled": "هذا الطلب تم إلغاؤه سابقاً.",
    "unsupported": "تعذر تحديد حالة الطلب حالياً، يرجى التواصل مع الموظف.",
}

WELCOME = "مرحباً بك، حدد ماذا تريد:"
MAIN_MENU = "\n".join(
    (
        "1- لمعرفة حالة طلب معين",
        "2- لمعرفة تكلفة طلب",
        "3- لمعرفة خطة القص لطلب معين",
        "4- لعرض قياسات طلب معين",
    )
)
UNREGISTERED = "عذراً رقمك غير مسجل بالنظام، قم بالتواصل مع الموظف من فضلك"
INVALID_MENU = "اختر 1 أو 2 أو 3 أو 4."
NO_CURRENT_ORDERS = "لا توجد طلبات غير مسلّمة. أدخل الرقم الكامل لطلب سابق إن أردت."
ASK_ORDER_NUMBER = "أدخل رقم الطلب الكامل، أو أرسل 0 للخدمات."
ORDER_NOT_FOUND = "لم يتم العثور على الطلب."
ORDER_NOT_CURRENT = "هذه النسخة ليست الطلب الحالي."
ORDER_CANCELLED = "هذا الطلب تم إلغاؤه سابقاً."
INVALID_ORDER_NUMBER = "أدخل رقم الطلب الكامل كما هو، أو أرسل 0 للخدمات."
SERVICE_UNAVAILABLE = "هذه الخدمة غير متاحة حالياً."


def render_message(key: str, parameters: tuple[tuple[str, str], ...]) -> str:
    values = dict(parameters)
    if key == "welcome":
        return WELCOME
    if key == "main_menu":
        return MAIN_MENU
    if key == "unregistered_phone":
        return UNREGISTERED
    if key == "invalid_menu_choice":
        return INVALID_MENU
    if key == "no_current_orders":
        return NO_CURRENT_ORDERS
    if key == "ask_order_number":
        return ASK_ORDER_NUMBER
    if key == "current_order_line":
        parts = [values["order_name"]]
        if values.get("order_date"):
            parts.append(values["order_date"])
        parts.append(STATUS_TEXT[values["public_status"]])
        return " ".join(parts)
    if key == "order_status":
        return f"{values['order_name']}: {STATUS_TEXT[values['public_status']]}"
    if key == "order_cancelled":
        return ORDER_CANCELLED
    if key == "order_not_found":
        return ORDER_NOT_FOUND
    if key == "order_not_current":
        return ORDER_NOT_CURRENT
    if key == "invalid_order_number":
        return INVALID_ORDER_NUMBER
    if key == "service_unavailable":
        return SERVICE_UNAVAILABLE
    raise KeyError(key)


def render_turn(messages: tuple[object, ...]) -> str:
    return "\n".join(
        render_message(message.key, message.parameters)  # type: ignore[attr-defined]
        for message in messages
    )
