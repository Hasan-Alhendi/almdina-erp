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
    "control_center",
    "reports",
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
        "description": "عرض التكلفة وتعديل إعداداتها واعتماد الأسعار الداخلية.",
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
    "control_center": {
        "label": "مركز التحكم والجودة",
        "description": "أرشفة الخطط وتسجيل الحوادث وإدارة قطع التعويض.",
        "icon": "dashboard",
    },
    "reports": {
        "label": "التقارير",
        "description": "عرض تقارير التشغيل والأداء والتكلفة والخسائر الداخلية.",
        "icon": "chart",
    },
    "administration": {
        "label": "الإدارة",
        "description": "إعدادات المعمل وإدارة المستخدمين ومصفوفة الصلاحيات.",
        "icon": "setting-gear",
    },
}


def _presentation(label: str, description: str, risk: str = "normal") -> dict[str, str]:
    return {"label": label, "description": description, "risk": risk}


CAPABILITY_PRESENTATION: dict[str, dict[str, str]] = {
    Capability.VIEW_ORDERS: _presentation("عرض الطلبات", "عرض الطلبات المسموح بها وفتح تفاصيلها الأساسية."),
    Capability.CREATE_ORDER: _presentation("إنشاء طلب", "إنشاء طلبات قص جديدة."),
    Capability.EDIT_ORDER: _presentation("تعديل الطلب", "تعديل الطلبات الموجودة في الحالات القابلة للتحرير.", "sensitive"),
    Capability.CREATE_ORDER_REVISION: _presentation("إنشاء نسخة تعديل", "إنشاء Revision جديد مع إبقاء الطلب التاريخي دون تغيير.", "sensitive"),
    Capability.SUBMIT_ORDER: _presentation("إرسال للمراجعة", "نقل الطلب من المسودة إلى قائمة المراجعة."),
    Capability.APPROVE_ORDER: _presentation("اعتماد الطلب", "اعتماد الطلب ليصبح جاهزًا للإنتاج.", "critical"),
    Capability.REJECT_ORDER: _presentation("رفض الطلب", "رفض الطلب الموجود في قائمة المراجعة وإعادته للتعديل.", "critical"),
    Capability.CANCEL_ORDER: _presentation("إلغاء الطلب", "إلغاء الطلب وفق ضوابط دورة الحياة.", "critical"),
    Capability.VIEW_COSTS: _presentation("عرض التكلفة", "عرض بيانات التكلفة والأسعار والربحية المحمية.", "sensitive"),
    Capability.EDIT_COST_SETTINGS: _presentation("تعديل إعدادات التكلفة", "تعديل سعر اللوح وأجرة القص وإعادة حساب التكلفة.", "critical"),
    Capability.EDIT_SPECIAL_PRICE: _presentation("تعديل سعر معتمد", "تغيير سعر درفة خاصة بعد اعتماده سابقًا.", "critical"),
    Capability.APPROVE_SPECIAL_PRICE: _presentation("اعتماد سعر خاص", "اعتماد السعر النهائي للدرف الخاصة.", "critical"),
    Capability.EDIT_REPLACEMENT_COST: _presentation("تعديل خسارة التعويض", "إدخال التكلفة الفعلية الداخلية عند إكمال قطعة التعويض.", "critical"),
    Capability.PRINT_MEASUREMENTS: _presentation("طباعة القياسات", "طباعة مستند القياسات دون أي أسعار."),
    Capability.PRINT_CUSTOMER_INVOICE: _presentation("طباعة فاتورة الزبون", "طباعة مستند الزبون المالي دون البيانات الداخلية.", "sensitive"),
    Capability.PRINT_INTERNAL_COST_REPORT: _presentation("طباعة تقرير التكلفة الداخلي", "طباعة التقرير السري الذي يتضمن التكلفة والخسائر والربحية.", "critical"),
    Capability.VIEW_CUTTING_PLAN: _presentation("عرض خطة القص", "عرض رسومات الخطة وبيانات ألواح القص."),
    Capability.RECALCULATE_PLAN: _presentation("إعادة حساب الخطة", "إعادة تشغيل محرك توزيع القطع على الألواح.", "sensitive"),
    Capability.EDIT_OPTIMIZER_SETTINGS: _presentation("تعديل إعدادات المحسّن", "تغيير الخوارزمية والهوامش وKerf وإعدادات البحث.", "sensitive"),
    Capability.PRINT_CUTTING_PLAN: _presentation("طباعة خطة القص", "طباعة الخطة المصرح بعرضها."),
    Capability.VIEW_DRAWING_WORKSPACE: _presentation("فتح مساحة الرسم", "عرض أدوات الرسم الخاصة وخطة DXF."),
    Capability.EDIT_SPECIAL_DRAWING: _presentation("تعديل الرسم الخاص", "تحرير هندسة وملاحظات الدرف الخاصة.", "sensitive"),
    Capability.EXPORT_DXF: _presentation("تصدير DXF", "تصدير رسم الإنتاج بصيغة DXF.", "sensitive"),
    Capability.UPLOAD_DXF: _presentation("رفع DXF", "رفع خطة DXF مخصصة للطلب.", "sensitive"),
    Capability.REPLACE_DXF: _presentation("استبدال DXF", "استبدال ملف DXF المرفوع سابقًا.", "critical"),
    Capability.APPROVE_DXF: _presentation("اعتماد الرسم", "اعتماد خطة النظام أو الخطة المرفوعة كمصدر للإنتاج.", "critical"),
    Capability.DISPATCH_ORDER: _presentation("إرسال الطلب للإنتاج", "اختيار مسار الإنتاج والعامل الأول وإنشاء المراحل.", "critical"),
    Capability.START_ASSIGNED_STAGE: _presentation("بدء المرحلة المسندة", "بدء المرحلة الحالية عندما تكون مسندة للمستخدم نفسه."),
    Capability.HANDOFF_ASSIGNED_STAGE: _presentation("تسليم المرحلة المسندة", "إنهاء المرحلة وإرسال الطلب إلى العامل التالي."),
    Capability.REVERT_DEPARTMENT: _presentation("إرجاع الطلب لقسم سابق", "إعادة الطلب إلى مرحلة أو قسم سابق مع سجل تدقيق.", "critical"),
    Capability.RETURN_ORDER_TO_DRAFT: _presentation("إعادة الطلب للمسودة", "إعادة الطلب إلى حالة قابلة للتعديل وفق السياسة.", "critical"),
    Capability.MARK_DELIVERED: _presentation("تأكيد التسليم", "تغيير حالة الطلب إلى تم التسليم.", "critical"),
    Capability.REASSIGN_WORKER: _presentation("تغيير العامل", "إعادة إسناد المرحلة الحالية إلى عامل مؤهل آخر.", "sensitive"),
    Capability.ARCHIVE_APPROVED_PLAN: _presentation("أرشفة الخطة المعتمدة", "إنشاء وحفظ PDF رسمي خاص بالخطة المعتمدة.", "sensitive"),
    Capability.RECORD_INCIDENT: _presentation("تسجيل حادث إنتاج", "تسجيل قطعة متضررة أو مشكلة أثناء التنفيذ.", "sensitive"),
    Capability.CREATE_REPLACEMENT: _presentation("إنشاء قطعة تعويض", "إنشاء قطعة تعويض من حادث إنتاج مسجل.", "sensitive"),
    Capability.VIEW_REPLACEMENTS: _presentation("عرض قطع التعويض", "فتح قطع التعويض ومتابعة حالتها."),
    Capability.APPROVE_REPLACEMENT: _presentation("اعتماد قطعة التعويض", "اعتماد القطعة وإنشاء خطة القص المصغرة وتجميد تكلفتها المتوقعة.", "critical"),
    Capability.START_REPLACEMENT: _presentation("بدء قطعة التعويض", "بدء تنفيذ قطعة تعويض معتمدة."),
    Capability.COMPLETE_REPLACEMENT: _presentation("إكمال قطعة التعويض", "إنهاء قطعة التعويض وتحديث حالة الطلب."),
    Capability.CANCEL_REPLACEMENT: _presentation("إلغاء قطعة التعويض", "إلغاء قطعة تعويض لم يبدأ تنفيذها بعد.", "critical"),
    Capability.VIEW_OPERATIONAL_REPORTS: _presentation("عرض التقارير التشغيلية", "عرض الأداء والمراحل والحوادث دون التكلفة والخسائر المالية.", "sensitive"),
    Capability.VIEW_FINANCIAL_REPORTS: _presentation("عرض التقارير المالية الداخلية", "عرض التكلفة الفعلية والهدر والخسائر الداخلية داخل التقارير.", "critical"),
    Capability.MANAGE_FACTORY_SETTINGS: _presentation("إدارة إعدادات المعمل", "تعديل إعدادات الإنتاج والمحسّن والتسعير الافتراضية.", "critical"),
    Capability.MANAGE_USERS: _presentation("إدارة المستخدمين", "إنشاء مستخدمي المعمل وتعديل حساباتهم وإسناد أدوارهم.", "critical"),
    Capability.MANAGE_PERMISSIONS: _presentation("إدارة الصلاحيات", "تعديل مصفوفة الصلاحيات لجميع الأدوار.", "critical"),
}


_REPLACEMENT_ACTIONS = frozenset(
    {
        Capability.APPROVE_REPLACEMENT,
        Capability.START_REPLACEMENT,
        Capability.COMPLETE_REPLACEMENT,
        Capability.CANCEL_REPLACEMENT,
        Capability.EDIT_REPLACEMENT_COST,
    }
)


def normalize_capability_state(raw: Mapping[str, Any] | None) -> dict[str, bool]:
    """Normalize a role matrix and enforce cross-capability dependencies."""

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

    if any(state[capability] for capability in _REPLACEMENT_ACTIONS):
        state[Capability.VIEW_REPLACEMENTS] = True

    if state[Capability.ARCHIVE_APPROVED_PLAN]:
        state[Capability.VIEW_CUTTING_PLAN] = True
        state[Capability.PRINT_CUTTING_PLAN] = True

    if state[Capability.VIEW_FINANCIAL_REPORTS]:
        state[Capability.VIEW_OPERATIONAL_REPORTS] = True
        state[Capability.VIEW_COSTS] = True

    return state


def standard_permission_projection(
    doctype: str,
    state: Mapping[str, Any] | None,
) -> dict[str, bool]:
    """Project business grants onto the standard Frappe permission columns."""

    normalized = normalize_capability_state(state)
    enabled_for_doctype = any(
        normalized[capability]
        for capability, definition in CAPABILITY_CATALOG.items()
        if definition.applies_to == doctype
    )
    if doctype == "Door Cutting Order":
        return {
            "read": normalized[Capability.VIEW_ORDERS],
            "create": normalized[Capability.CREATE_ORDER],
            "write": normalized[Capability.EDIT_ORDER],
        }
    if doctype == "Almdina ERP Settings":
        return {
            "read": enabled_for_doctype,
            "create": False,
            "write": normalized[Capability.MANAGE_FACTORY_SETTINGS],
        }
    if doctype == "Replacement Piece":
        return {"read": enabled_for_doctype, "create": False, "write": False}
    return {"read": enabled_for_doctype, "create": False, "write": False}


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
    "standard_permission_projection",
]
