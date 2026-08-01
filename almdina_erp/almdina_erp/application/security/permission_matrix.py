from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from almdina_erp.almdina_erp.application.security.navigation_context import (
    build_navigation_context,
)
from almdina_erp.almdina_erp.domain.security.authorization import (
    ALL_CAPABILITIES,
    CAPABILITY_CATALOG,
    Capability,
    normalize_capabilities,
)


CATEGORY_ORDER = (
    "order",
    "costing",
    "documents",
    "cutting_plan",
    "drawing",
    "production",
    "administration",
)

CATEGORY_PRESENTATION: dict[str, dict[str, str]] = {
    "order": {
        "label": "الطلبات",
        "description": "إنشاء الطلب ومراجعته واعتماده وإدارة دورة حياته.",
        "icon": "file-text",
    },
    "costing": {
        "label": "التكلفة والتسعير",
        "description": "عرض التكلفة وتعديل إعداداتها واعتماد أسعار الدرف الخاصة.",
        "icon": "accounting",
    },
    "documents": {
        "label": "المستندات والطباعة",
        "description": "طباعة القياسات وفاتورة الزبون والتقرير الداخلي السري.",
        "icon": "printer",
    },
    "cutting_plan": {
        "label": "خطة القص",
        "description": "عرض الخطة وحسابها وتعديل إعدادات المحسّن وطباعتها.",
        "icon": "organization",
    },
    "drawing": {
        "label": "الرسم وDXF",
        "description": "الرسم الخاص وتصدير ملفات DXF ورفعها واستبدالها واعتمادها.",
        "icon": "image-view",
    },
    "production": {
        "label": "الإنتاج والإسناد",
        "description": "إرسال الطلب وبدء المراحل وتسليمها والرجوع وإعادة الإسناد.",
        "icon": "tool",
    },
    "administration": {
        "label": "الإدارة",
        "description": "إعدادات المعمل وإدارة المستخدمين ومصفوفة الصلاحيات.",
        "icon": "setting-gear",
    },
}

CAPABILITY_PRESENTATION: dict[str, dict[str, str]] = {
    Capability.VIEW_ORDERS: {
        "label": "عرض الطلبات",
        "description": "عرض الطلبات المسموح بها وفتح تفاصيلها الأساسية.",
        "risk": "normal",
    },
    Capability.CREATE_ORDER: {
        "label": "إنشاء طلب",
        "description": "إنشاء طلبات قص جديدة.",
        "risk": "normal",
    },
    Capability.EDIT_ORDER: {
        "label": "تعديل الطلب",
        "description": "تعديل الطلبات الموجودة في الحالات القابلة للتحرير.",
        "risk": "sensitive",
    },
    Capability.CREATE_ORDER_REVISION: {
        "label": "إنشاء نسخة تعديل",
        "description": "إنشاء Revision جديد مع إبقاء الطلب التاريخي دون تغيير.",
        "risk": "sensitive",
    },
    Capability.SUBMIT_ORDER: {
        "label": "إرسال للمراجعة",
        "description": "نقل الطلب من المسودة إلى قائمة المراجعة.",
        "risk": "normal",
    },
    Capability.APPROVE_ORDER: {
        "label": "اعتماد الطلب",
        "description": "اعتماد الطلب ليصبح جاهزًا للإنتاج.",
        "risk": "critical",
    },
    Capability.CANCEL_ORDER: {
        "label": "إلغاء الطلب",
        "description": "إلغاء الطلب وفق ضوابط دورة الحياة.",
        "risk": "critical",
    },
    Capability.VIEW_COSTS: {
        "label": "عرض التكلفة",
        "description": "عرض بيانات التكلفة والأسعار والربحية المحمية.",
        "risk": "sensitive",
    },
    Capability.EDIT_COST_SETTINGS: {
        "label": "تعديل إعدادات التكلفة",
        "description": "تعديل سعر اللوح وأجرة القص وإعادة حساب التكلفة.",
        "risk": "critical",
    },
    Capability.EDIT_SPECIAL_PRICE: {
        "label": "تعديل سعر معتمد",
        "description": "تغيير سعر درفة خاصة بعد اعتماده سابقًا.",
        "risk": "critical",
    },
    Capability.APPROVE_SPECIAL_PRICE: {
        "label": "اعتماد سعر خاص",
        "description": "اعتماد السعر النهائي للدرف الخاصة.",
        "risk": "critical",
    },
    Capability.PRINT_MEASUREMENTS: {
        "label": "طباعة القياسات",
        "description": "طباعة مستند القياسات دون أي أسعار.",
        "risk": "normal",
    },
    Capability.PRINT_CUSTOMER_INVOICE: {
        "label": "طباعة فاتورة الزبون",
        "description": "طباعة مستند الزبون المالي دون البيانات الداخلية.",
        "risk": "sensitive",
    },
    Capability.PRINT_INTERNAL_COST_REPORT: {
        "label": "طباعة تقرير التكلفة الداخلي",
        "description": "طباعة التقرير السري الذي يتضمن التكلفة والخسائر والربحية.",
        "risk": "critical",
    },
    Capability.VIEW_CUTTING_PLAN: {
        "label": "عرض خطة القص",
        "description": "عرض رسومات الخطة وبيانات ألواح القص.",
        "risk": "normal",
    },
    Capability.RECALCULATE_PLAN: {
        "label": "إعادة حساب الخطة",
        "description": "إعادة تشغيل محرك توزيع القطع على الألواح.",
        "risk": "sensitive",
    },
    Capability.EDIT_OPTIMIZER_SETTINGS: {
        "label": "تعديل إعدادات المحسّن",
        "description": "تغيير الخوارزمية والهوامش وKerf وإعدادات البحث.",
        "risk": "sensitive",
    },
    Capability.PRINT_CUTTING_PLAN: {
        "label": "طباعة خطة القص",
        "description": "طباعة الخطة المصرح بعرضها.",
        "risk": "normal",
    },
    Capability.VIEW_DRAWING_WORKSPACE: {
        "label": "فتح مساحة الرسم",
        "description": "عرض أدوات الرسم الخاصة وخطة DXF.",
        "risk": "normal",
    },
    Capability.EDIT_SPECIAL_DRAWING: {
        "label": "تعديل الرسم الخاص",
        "description": "تحرير هندسة وملاحظات الدرف الخاصة.",
        "risk": "sensitive",
    },
    Capability.EXPORT_DXF: {
        "label": "تصدير DXF",
        "description": "تصدير رسم الإنتاج بصيغة DXF.",
        "risk": "sensitive",
    },
    Capability.UPLOAD_DXF: {
        "label": "رفع DXF",
        "description": "رفع خطة DXF مخصصة للطلب.",
        "risk": "sensitive",
    },
    Capability.REPLACE_DXF: {
        "label": "استبدال DXF",
        "description": "استبدال ملف DXF المرفوع سابقًا.",
        "risk": "critical",
    },
    Capability.APPROVE_DXF: {
        "label": "اعتماد الرسم",
        "description": "اعتماد خطة النظام أو الخطة المرفوعة كمصدر للإنتاج.",
        "risk": "critical",
    },
    Capability.DISPATCH_ORDER: {
        "label": "إرسال الطلب للإنتاج",
        "description": "اختيار مسار الإنتاج والعامل الأول وإنشاء المراحل.",
        "risk": "critical",
    },
    Capability.START_ASSIGNED_STAGE: {
        "label": "بدء المرحلة المسندة",
        "description": "بدء المرحلة الحالية عندما تكون مسندة للمستخدم نفسه.",
        "risk": "normal",
    },
    Capability.HANDOFF_ASSIGNED_STAGE: {
        "label": "تسليم المرحلة المسندة",
        "description": "إنهاء المرحلة وإرسال الطلب إلى العامل التالي.",
        "risk": "normal",
    },
    Capability.REVERT_DEPARTMENT: {
        "label": "إرجاع الطلب لقسم سابق",
        "description": "إعادة الطلب إلى مرحلة أو قسم سابق مع سجل تدقيق.",
        "risk": "critical",
    },
    Capability.RETURN_ORDER_TO_DRAFT: {
        "label": "إعادة الطلب للمسودة",
        "description": "إعادة الطلب إلى حالة قابلة للتعديل وفق السياسة.",
        "risk": "critical",
    },
    Capability.MARK_DELIVERED: {
        "label": "تأكيد التسليم",
        "description": "تغيير حالة الطلب إلى تم التسليم.",
        "risk": "critical",
    },
    Capability.REASSIGN_WORKER: {
        "label": "تغيير العامل",
        "description": "إعادة إسناد المرحلة الحالية إلى عامل مؤهل آخر.",
        "risk": "sensitive",
    },
    Capability.MANAGE_FACTORY_SETTINGS: {
        "label": "إدارة إعدادات المعمل",
        "description": "تعديل إعدادات الإنتاج والمحسّن والتسعير الافتراضية.",
        "risk": "critical",
    },
    Capability.MANAGE_USERS: {
        "label": "إدارة المستخدمين",
        "description": "إنشاء مستخدمي المعمل وتعديل حساباتهم وإسناد أدوارهم.",
        "risk": "critical",
    },
    Capability.MANAGE_PERMISSIONS: {
        "label": "إدارة الصلاحيات",
        "description": "تعديل مصفوفة الصلاحيات لجميع الأدوار.",
        "risk": "critical",
    },
}


def normalize_capability_state(raw: Mapping[str, Any] | None) -> dict[str, bool]:
    """Normalize a role matrix and enforce the document-read dependency."""

    supplied = {str(key): value for key, value in dict(raw or {}).items()}
    unknown = set(supplied).difference(ALL_CAPABILITIES)
    if unknown:
        raise ValueError(f"Unknown capabilities: {', '.join(sorted(unknown))}")

    state = {
        capability: supplied.get(capability) is True
        for capability in sorted(ALL_CAPABILITIES)
    }
    order_actions = {
        capability
        for capability, enabled in state.items()
        if enabled
        and CAPABILITY_CATALOG[capability].applies_to == "Door Cutting Order"
        and capability != Capability.VIEW_ORDERS
    }
    if order_actions:
        state[Capability.VIEW_ORDERS] = True
    return state


def enabled_capabilities(state: Mapping[str, Any] | None) -> frozenset[str]:
    normalized = normalize_capability_state(state)
    return normalize_capabilities(
        capability for capability, enabled in normalized.items() if enabled
    )


def capability_catalog_payload() -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    for category in CATEGORY_ORDER:
        category_meta = CATEGORY_PRESENTATION[category]
        capabilities: list[dict[str, Any]] = []
        for capability, definition in CAPABILITY_CATALOG.items():
            if definition.category != category:
                continue
            presentation = CAPABILITY_PRESENTATION[capability]
            capabilities.append(
                {
                    "key": capability,
                    "label": presentation["label"],
                    "description": presentation["description"],
                    "risk": presentation["risk"],
                    "permission_type": definition.permission_type,
                    "doctype": definition.applies_to,
                    "standard": not definition.custom,
                }
            )
        groups.append(
            {
                "key": category,
                "label": category_meta["label"],
                "description": category_meta["description"],
                "icon": category_meta["icon"],
                "capabilities": capabilities,
            }
        )
    return groups


def permission_impact(state: Mapping[str, Any] | None) -> dict[str, Any]:
    normalized = normalize_capability_state(state)
    granted = enabled_capabilities(normalized)
    navigation = build_navigation_context(granted)
    critical = sorted(
        capability
        for capability in granted
        if CAPABILITY_PRESENTATION[capability]["risk"] == "critical"
    )
    return {
        "enabled_count": len(granted),
        "critical_count": len(critical),
        "critical_capabilities": critical,
        "navigation": navigation,
    }


def changed_capabilities(
    before: Mapping[str, Any] | None,
    after: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    old = normalize_capability_state(before)
    new = normalize_capability_state(after)
    changes: list[dict[str, Any]] = []
    for capability in sorted(ALL_CAPABILITIES):
        if old[capability] == new[capability]:
            continue
        presentation = CAPABILITY_PRESENTATION[capability]
        changes.append(
            {
                "key": capability,
                "label": presentation["label"],
                "risk": presentation["risk"],
                "before": old[capability],
                "after": new[capability],
            }
        )
    return changes


__all__ = [
    "CAPABILITY_PRESENTATION",
    "CATEGORY_ORDER",
    "CATEGORY_PRESENTATION",
    "capability_catalog_payload",
    "changed_capabilities",
    "enabled_capabilities",
    "normalize_capability_state",
    "permission_impact",
]
