from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Any

from almdina_erp.almdina_erp.application.security.navigation_context import build_navigation_context
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
    "workforce",
    "factory_settings",
    "master_data",
    "administration",
)

CATEGORY_PRESENTATION: dict[str, dict[str, str]] = {
    "order": {"label": "الطلبات", "description": "إنشاء الطلب ومراجعته واعتماده وإدارة دورة حياته.", "icon": "file-text"},
    "costing": {"label": "التكلفة والتسعير", "description": "عرض التكلفة وتعديل إعداداتها واعتماد الأسعار الداخلية.", "icon": "accounting"},
    "documents": {"label": "المستندات والطباعة", "description": "طباعة القياسات وفاتورة الزبون والتقرير الداخلي السري.", "icon": "printer"},
    "cutting_plan": {"label": "خطة القص", "description": "عرض الخطة وحسابها وتعديل إعدادات المحسّن وطباعتها.", "icon": "organization"},
    "drawing": {"label": "الرسم وDXF", "description": "الرسم الخاص وتصدير ملفات DXF ورفعها واستبدالها واعتمادها.", "icon": "image-view"},
    "production": {"label": "الإنتاج والإسناد", "description": "إرسال الطلب وبدء المراحل وتسليمها والرجوع وإعادة الإسناد.", "icon": "tool"},
    "control_center": {"label": "مركز التحكم والجودة", "description": "أرشفة الخطط وتسجيل الحوادث وإدارة قطع التعويض.", "icon": "dashboard"},
    "reports": {"label": "التقارير", "description": "عرض تقارير التشغيل والأداء والتكلفة والخسائر الداخلية.", "icon": "chart"},
    "workforce": {"label": "المستخدمون والقوى العاملة", "description": "عرض حسابات المعمل وإنشاؤها وتعديلها وتفعيلها وإسناد أدوارها.", "icon": "users"},
    "factory_settings": {"label": "إعدادات المعمل", "description": "عرض وتعديل إعدادات القص والتكلفة وضوابط الإنتاج كل قسم بصورة مستقلة.", "icon": "setting-gear"},
    "master_data": {"label": "البيانات الأساسية", "description": "إدارة مسارات الإنتاج وأنواع القشاط مع فصل العرض والإنشاء والتعديل والحذف.", "icon": "database"},
    "administration": {"label": "الأدوار والصلاحيات", "description": "فصل عرض الأدوار وإنشائها وتعديلها وحذفها عن تعديل مصفوفة الصلاحيات.", "icon": "lock"},
}


def _presentation(label: str, description: str, risk: str = "normal") -> dict[str, str]:
    return {"label": label, "description": description, "risk": risk}


CAPABILITY_PRESENTATION: dict[str, dict[str, str]] = {
    Capability.VIEW_ORDERS: _presentation("عرض الطلبات", "عرض الطلبات المسموح بها وفتح تفاصيلها الأساسية."),
    Capability.CREATE_ORDER: _presentation("إنشاء طلب", "إنشاء طلبات قص جديدة."),
    Capability.EDIT_ORDER: _presentation("تعديل الطلب", "تعديل الطلب وفق سياسة دورة الحياة.", "sensitive"),
    Capability.CREATE_ORDER_REVISION: _presentation("إنشاء نسخة تعديل", "إنشاء Revision جديد مع إبقاء الطلب التاريخي دون تغيير.", "sensitive"),
    Capability.SUBMIT_ORDER: _presentation("إرسال للمراجعة", "نقل الطلب من المسودة إلى قائمة المراجعة."),
    Capability.APPROVE_ORDER: _presentation("اعتماد الطلب", "اعتماد الطلب ليصبح جاهزًا للإنتاج.", "critical"),
    Capability.REJECT_ORDER: _presentation("رفض الطلب", "رفض الطلب وإعادته للتعديل.", "critical"),
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
    Capability.UPLOAD_DXF: _presentation("رفع خطة قص DXF", "رفع خطة قص كملف DXF مع التحقق قبل اعتمادها.", "sensitive"),
    Capability.REPLACE_DXF: _presentation("استبدال خطة قص DXF", "استبدال ملف DXF المرفوع سابقًا بعد التحقق.", "critical"),
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
    Capability.VIEW_USERS: _presentation("عرض مستخدمي المعمل", "عرض حسابات Almdina وحالتها والأدوار المسندة إليها."),
    Capability.CREATE_USERS: _presentation("إنشاء مستخدم", "إنشاء حساب نظام جديد للمعمل مع كلمة مرور مؤقتة.", "critical"),
    Capability.EDIT_USERS: _presentation("تعديل بيانات المستخدم", "تعديل الاسم واللغة وبيانات الحساب غير المالية.", "sensitive"),
    Capability.ASSIGN_USER_ROLES: _presentation("إسناد أدوار المستخدم", "إضافة أو إزالة أدوار Almdina المسموح بإدارتها للمستخدم.", "critical"),
    Capability.ENABLE_USERS: _presentation("تفعيل المستخدم", "إعادة تفعيل حساب معمل معطّل.", "critical"),
    Capability.DISABLE_USERS: _presentation("تعطيل المستخدم", "تعطيل حساب بعد التأكد من عدم وجود مراحل إنتاج نشطة.", "critical"),
    Capability.RESET_USER_PASSWORD: _presentation("إعادة كلمة المرور", "تعيين كلمة مرور مؤقتة جديدة دون تخزينها في السجل.", "critical"),
    Capability.VIEW_FACTORY_SETTINGS: _presentation("عرض إعدادات المعمل", "عرض إعدادات القص والتكلفة وضوابط الإنتاج دون تعديل."),
    Capability.EDIT_FACTORY_CUTTING_DEFAULTS: _presentation("تعديل افتراضيات القص", "تعديل Kerf والهامش والخوارزمية ونوع الآلة وحدود البحث.", "sensitive"),
    Capability.EDIT_FACTORY_COST_DEFAULTS: _presentation("تعديل افتراضيات التكلفة", "تعديل أجرة القص ورسوم الدرف الخاصة وهوامشها.", "critical"),
    Capability.EDIT_FACTORY_PRODUCTION_CONTROLS: _presentation("تعديل ضوابط الإنتاج", "تعديل المسار الافتراضي والاستثناءات التشغيلية الحساسة.", "critical"),
    Capability.VIEW_PRODUCTION_ROUTINGS: _presentation("عرض مسارات الإنتاج", "عرض مسارات الإنتاج وتسلسل مراحلها."),
    Capability.CREATE_PRODUCTION_ROUTINGS: _presentation("إنشاء مسار إنتاج", "إنشاء مسار إنتاج جديد.", "sensitive"),
    Capability.EDIT_PRODUCTION_ROUTINGS: _presentation("تعديل مسارات الإنتاج", "تعديل ترتيب المراحل أو تعطيل المسار.", "critical"),
    Capability.DELETE_PRODUCTION_ROUTINGS: _presentation("حذف مسار إنتاج", "حذف مسار غير مستخدم وغير معيّن كافتراضي.", "critical"),
    Capability.VIEW_CUSTOMERS: _presentation("عرض الزبائن للطلبات", "اختيار الزبون وعرض اسمه عند إنشاء الطلب أو تعديله."),
    Capability.VIEW_EDGE_BANDING_TYPES: _presentation("عرض أنواع القشاط", "عرض أنواع القشاط والسماكة والسعر والحالة."),
    Capability.CREATE_EDGE_BANDING_TYPES: _presentation("إنشاء نوع قشاط", "إضافة نوع قشاط جديد.", "sensitive"),
    Capability.EDIT_EDGE_BANDING_TYPES: _presentation("تعديل أنواع القشاط", "تعديل السماكة والسعر والخصائص أو تعطيل النوع.", "critical"),
    Capability.DELETE_EDGE_BANDING_TYPES: _presentation("حذف نوع قشاط", "حذف نوع غير مستخدم في أي طلب أو قطعة.", "critical"),
    Capability.VIEW_ROLES: _presentation("عرض الأدوار", "عرض أدوار Almdina وتفاصيل استخدامها دون تعديل."),
    Capability.CREATE_ROLES: _presentation("إنشاء الأدوار", "إنشاء دور Almdina جديد فارغ دون أي صلاحيات تلقائية.", "critical"),
    Capability.EDIT_ROLES: _presentation("تعديل الأدوار", "تعديل اسم الدور ووصفه وتفعيله أو تعطيله وفق قيود الاستخدام.", "critical"),
    Capability.DELETE_ROLES: _presentation("حذف الأدوار", "حذف دور Almdina غير مستخدم بعد فحص جميع المراجع.", "critical"),
    Capability.MANAGE_PERMISSIONS: _presentation("إدارة الصلاحيات", "تعديل مصفوفة الصلاحيات يدويًا للأدوار.", "critical"),
}


def _build_prerequisites() -> MappingProxyType:
    direct: dict[str, set[str]] = {capability: set() for capability in ALL_CAPABILITIES}

    # Any action on an order requires explicit visibility of the order itself.
    for capability, definition in CAPABILITY_CATALOG.items():
        if definition.applies_to == "Door Cutting Order" and capability != Capability.VIEW_ORDERS:
            direct[capability].add(Capability.VIEW_ORDERS)
        if definition.applies_to == "Replacement Piece" and capability != Capability.VIEW_REPLACEMENTS:
            direct[capability].add(Capability.VIEW_REPLACEMENTS)

    for capability in (
        Capability.EDIT_COST_SETTINGS,
        Capability.EDIT_SPECIAL_PRICE,
        Capability.APPROVE_SPECIAL_PRICE,
        Capability.PRINT_INTERNAL_COST_REPORT,
    ):
        direct[capability].add(Capability.VIEW_COSTS)
    for capability in (
        Capability.RECALCULATE_PLAN,
        Capability.EDIT_OPTIMIZER_SETTINGS,
        Capability.PRINT_CUTTING_PLAN,
    ):
        direct[capability].add(Capability.VIEW_CUTTING_PLAN)
    for capability in (
        Capability.EDIT_SPECIAL_DRAWING,
        Capability.EXPORT_DXF,
        Capability.UPLOAD_DXF,
        Capability.REPLACE_DXF,
        Capability.APPROVE_DXF,
    ):
        direct[capability].add(Capability.VIEW_DRAWING_WORKSPACE)
    direct[Capability.ARCHIVE_APPROVED_PLAN].update(
        {Capability.VIEW_CUTTING_PLAN, Capability.PRINT_CUTTING_PLAN}
    )
    direct[Capability.VIEW_FINANCIAL_REPORTS].update(
        {Capability.VIEW_OPERATIONAL_REPORTS, Capability.VIEW_COSTS}
    )
    for capability in (
        Capability.CREATE_USERS,
        Capability.EDIT_USERS,
        Capability.ASSIGN_USER_ROLES,
        Capability.ENABLE_USERS,
        Capability.DISABLE_USERS,
        Capability.RESET_USER_PASSWORD,
    ):
        direct[capability].add(Capability.VIEW_USERS)
    direct[Capability.ASSIGN_USER_ROLES].add(Capability.VIEW_ROLES)
    for capability in (
        Capability.CREATE_ROLES,
        Capability.EDIT_ROLES,
        Capability.DELETE_ROLES,
        Capability.MANAGE_PERMISSIONS,
    ):
        direct[capability].add(Capability.VIEW_ROLES)
    for capability in (
        Capability.EDIT_FACTORY_CUTTING_DEFAULTS,
        Capability.EDIT_FACTORY_COST_DEFAULTS,
        Capability.EDIT_FACTORY_PRODUCTION_CONTROLS,
    ):
        direct[capability].add(Capability.VIEW_FACTORY_SETTINGS)
    direct[Capability.EDIT_FACTORY_PRODUCTION_CONTROLS].add(
        Capability.VIEW_PRODUCTION_ROUTINGS
    )
    for capability in (
        Capability.CREATE_PRODUCTION_ROUTINGS,
        Capability.EDIT_PRODUCTION_ROUTINGS,
        Capability.DELETE_PRODUCTION_ROUTINGS,
    ):
        direct[capability].add(Capability.VIEW_PRODUCTION_ROUTINGS)
    for capability in (
        Capability.CREATE_EDGE_BANDING_TYPES,
        Capability.EDIT_EDGE_BANDING_TYPES,
        Capability.DELETE_EDGE_BANDING_TYPES,
    ):
        direct[capability].add(Capability.VIEW_EDGE_BANDING_TYPES)
    for capability in (
        Capability.CREATE_ORDER,
        Capability.EDIT_ORDER,
        Capability.CREATE_ORDER_REVISION,
    ):
        direct[capability].update(
            {Capability.VIEW_CUSTOMERS, Capability.VIEW_EDGE_BANDING_TYPES}
        )

    return MappingProxyType(
        {capability: frozenset(values) for capability, values in direct.items()}
    )


CAPABILITY_PREREQUISITES = _build_prerequisites()


def normalize_capability_state(raw: Mapping[str, Any] | None) -> dict[str, bool]:
    """Normalize the exact administrator selection without granting dependencies."""

    supplied = {str(key): value for key, value in dict(raw or {}).items()}
    unknown = set(supplied).difference(ALL_CAPABILITIES)
    if unknown:
        raise ValueError(f"Unknown capabilities: {', '.join(sorted(unknown))}")
    return {
        capability: supplied.get(capability) is True
        for capability in sorted(ALL_CAPABILITIES)
    }


def required_capabilities(capability: str) -> frozenset[str]:
    if capability not in ALL_CAPABILITIES:
        raise ValueError(f"Unknown capability: {capability}")
    required: set[str] = set()
    pending = list(CAPABILITY_PREREQUISITES[capability])
    while pending:
        current = pending.pop()
        if current in required:
            continue
        required.add(current)
        pending.extend(CAPABILITY_PREREQUISITES[current])
    return frozenset(required)


def missing_capability_dependencies(
    state: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    normalized = normalize_capability_state(state)
    missing: list[dict[str, Any]] = []
    for capability in sorted(ALL_CAPABILITIES):
        if not normalized[capability]:
            continue
        absent = sorted(
            requirement
            for requirement in required_capabilities(capability)
            if not normalized[requirement]
        )
        if absent:
            missing.append(
                {
                    "capability": capability,
                    "label": CAPABILITY_PRESENTATION[capability]["label"],
                    "missing": absent,
                    "missing_labels": [
                        CAPABILITY_PRESENTATION[item]["label"] for item in absent
                    ],
                }
            )
    return missing


def validate_capability_dependencies(
    state: Mapping[str, Any] | None,
) -> dict[str, bool]:
    normalized = normalize_capability_state(state)
    missing = missing_capability_dependencies(normalized)
    if missing:
        details = "; ".join(
            f"{row['label']} requires {', '.join(row['missing_labels'])}"
            for row in missing
        )
        raise ValueError(f"Missing required permissions: {details}")
    return normalized


def standard_permission_projection(
    doctype: str,
    state: Mapping[str, Any] | None,
) -> dict[str, bool]:
    normalized = normalize_capability_state(state)
    if doctype == "Door Cutting Order":
        can_read = normalized[Capability.VIEW_ORDERS]
        return {"read": can_read, "select": can_read, "create": normalized[Capability.CREATE_ORDER], "write": normalized[Capability.EDIT_ORDER], "delete": False}
    if doctype == "Almdina ERP Settings":
        can_read = normalized[Capability.VIEW_FACTORY_SETTINGS]
        return {"read": can_read, "select": can_read, "create": False, "write": False, "delete": False}
    if doctype == "Replacement Piece":
        can_read = normalized[Capability.VIEW_REPLACEMENTS]
        return {"read": can_read, "select": can_read, "create": False, "write": False, "delete": False}
    if doctype == "Production Routing":
        can_read = normalized[Capability.VIEW_PRODUCTION_ROUTINGS]
        return {"read": can_read, "select": can_read, "create": normalized[Capability.CREATE_PRODUCTION_ROUTINGS], "write": normalized[Capability.EDIT_PRODUCTION_ROUTINGS], "delete": normalized[Capability.DELETE_PRODUCTION_ROUTINGS]}
    if doctype == "Customer":
        can_read = normalized[Capability.VIEW_CUSTOMERS]
        return {"read": can_read, "select": can_read, "create": False, "write": False, "delete": False}
    if doctype == "Edge Banding Type":
        can_read = normalized[Capability.VIEW_EDGE_BANDING_TYPES]
        return {"read": can_read, "select": can_read, "create": normalized[Capability.CREATE_EDGE_BANDING_TYPES], "write": normalized[Capability.EDIT_EDGE_BANDING_TYPES], "delete": normalized[Capability.DELETE_EDGE_BANDING_TYPES]}
    enabled = any(
        normalized[capability]
        for capability, definition in CAPABILITY_CATALOG.items()
        if definition.applies_to == doctype
    )
    return {"read": enabled, "select": enabled, "create": False, "write": False, "delete": False}


def field_permission_projection(
    doctype: str,
    state: Mapping[str, Any] | None,
) -> dict[int, dict[str, bool]]:
    normalized = normalize_capability_state(state)
    if doctype != "Door Cutting Order":
        return {}
    return {1: {"read": normalized[Capability.VIEW_COSTS], "write": normalized[Capability.EDIT_COST_SETTINGS]}}


def enabled_capabilities(state: Mapping[str, Any] | None) -> frozenset[str]:
    normalized = normalize_capability_state(state)
    return normalize_capabilities(
        capability for capability, enabled in normalized.items() if enabled
    )


def capability_catalog_payload() -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    for category in CATEGORY_ORDER:
        category_meta = CATEGORY_PRESENTATION[category]
        capabilities = []
        for capability, definition in CAPABILITY_CATALOG.items():
            if definition.category != category:
                continue
            presentation = CAPABILITY_PRESENTATION[capability]
            requires = sorted(required_capabilities(capability))
            capabilities.append(
                {
                    "key": capability,
                    "label": presentation["label"],
                    "description": presentation["description"],
                    "risk": presentation["risk"],
                    "permission_type": definition.permission_type,
                    "doctype": definition.applies_to,
                    "standard": not definition.custom,
                    "requires": requires,
                    "requires_labels": [CAPABILITY_PRESENTATION[item]["label"] for item in requires],
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
    normalized = validate_capability_dependencies(state)
    granted = enabled_capabilities(normalized)
    critical = sorted(
        capability
        for capability in granted
        if CAPABILITY_PRESENTATION[capability]["risk"] == "critical"
    )
    return {
        "enabled_count": len(granted),
        "critical_count": len(critical),
        "critical_capabilities": critical,
        "navigation": build_navigation_context(granted),
    }


def changed_capabilities(
    before: Mapping[str, Any] | None,
    after: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    old = normalize_capability_state(before)
    new = normalize_capability_state(after)
    changes = []
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
    "CAPABILITY_PREREQUISITES",
    "CAPABILITY_PRESENTATION",
    "CATEGORY_ORDER",
    "CATEGORY_PRESENTATION",
    "capability_catalog_payload",
    "changed_capabilities",
    "enabled_capabilities",
    "field_permission_projection",
    "missing_capability_dependencies",
    "normalize_capability_state",
    "permission_impact",
    "required_capabilities",
    "standard_permission_projection",
    "validate_capability_dependencies",
]
