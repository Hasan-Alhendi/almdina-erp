from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from almdina_erp.almdina_erp.application.security.navigation_context import build_navigation_context
from almdina_erp.almdina_erp.domain.security.authorization import (
    ALL_CAPABILITIES,
    CAPABILITY_CATALOG,
    CUTTING_PLAN_DOCTYPE,
    FACTORY_SETTINGS_CAPABILITIES,
    WORKFORCE_CAPABILITIES,
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
    "shop_floor",
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
    "cutting_plan": {"label": "خطة القص", "description": "عرض تبويبات الخطة (نظام / مرفوعة / معتمدة) وحسابها وتعديل إعدادات المحسّن واعتمادها وطباعتها.", "icon": "organization"},
    "drawing": {"label": "الرسم وDXF", "description": "الرسم الخاص وتصدير ملفات DXF ورفعها واستبدالها.", "icon": "image-view"},
    "production": {"label": "الإنتاج والإسناد", "description": "إرسال الطلب وبدء المراحل وتسليمها والرجوع وإعادة الإسناد.", "icon": "tool"},
    "shop_floor": {"label": "صالة الإنتاج", "description": "صلاحيات العرض الإضافية داخل صالة الإنتاج دون منح دخول أو إجراءات إنتاجية بحد ذاتها.", "icon": "list"},
    "control_center": {"label": "مركز التحكم والجودة", "description": "أرشفة الخطط وعرض حوادث الإنتاج وتسجيلها وإدارة قطع التعويض.", "icon": "dashboard"},
    "reports": {"label": "التقارير", "description": "عرض تقارير التشغيل والأداء والتكلفة والخسائر الداخلية.", "icon": "chart"},
    "workforce": {"label": "المستخدمون والقوى العاملة", "description": "عرض حسابات المعمل وإنشاؤها وتعديلها وتفعيلها وإدارة أدوارها.", "icon": "users"},
    "factory_settings": {"label": "إعدادات المعمل", "description": "عرض وتعديل إعدادات القص والتكلفة وضوابط الإنتاج وهوية أوراق الطباعة كل قسم بصورة مستقلة.", "icon": "setting-gear"},
    "master_data": {"label": "البيانات الأساسية", "description": "إدارة مسارات الإنتاج وأنواع القشاط مع فصل العرض والإنشاء والتعديل والحذف.", "icon": "database"},
    "administration": {"label": "إدارة الصلاحيات", "description": "تعديل مصفوفة الصلاحيات لجميع الأدوار.", "icon": "lock"},
}


def _presentation(label: str, description: str, risk: str = "normal") -> dict[str, str]:
    return {"label": label, "description": description, "risk": risk}


CAPABILITY_PRESENTATION: dict[str, dict[str, str]] = {
    Capability.VIEW_ORDERS: _presentation("عرض الطلبات", "عرض الطلبات المسموح بها وفتح تفاصيلها الأساسية."),
    Capability.VIEW_ALL_ORDERS: _presentation("عرض جميع الطلبات", "تجاوز نطاق الإسناد وعرض طلبات جميع العاملين. تُمنح للإدارة المخولة فقط.", "critical"),
    Capability.CREATE_ORDER: _presentation("إنشاء طلب", "إنشاء طلبات قص جديدة."),
    Capability.EDIT_ORDER: _presentation("تعديل الطلب", "تفعيل وضع التعديل على الطلب وهو في حالة المسودة فقط. بعد الإرسال للإنتاج استخدم إعادة للمسودة أو نسخة تعديل.", "sensitive"),
    Capability.CREATE_ORDER_REVISION: _presentation("إنشاء نسخة تعديل", "إنشاء Revision جديد مع إبقاء الطلب التاريخي دون تغيير.", "sensitive"),
    Capability.SUBMIT_ORDER: _presentation("إرسال للمراجعة (ملغاة)", "أُلغيت. الطلب يُرسل مباشرة إلى الإنتاج دون مرور بالمراجعة."),
    Capability.APPROVE_ORDER: _presentation("اعتماد الطلب (ملغاة)", "أُلغيت. استخدم «إرسال للإنتاج» مباشرة. اعتماد خطة القص يبقى صلاحية منفصلة.", "critical"),
    Capability.REJECT_ORDER: _presentation("رفض الطلب", "رفض طلب عالق في قائمة المراجعة القديمة وإعادته للتعديل.", "critical"),
    Capability.CANCEL_ORDER: _presentation("إلغاء الطلب", "إلغاء الطلب وفق ضوابط دورة الحياة.", "critical"),
    Capability.VIEW_COSTS: _presentation("عرض التكلفة", "عرض بيانات التكلفة والأسعار والربحية المحمية.", "sensitive"),
    Capability.EDIT_COST_SETTINGS: _presentation("تعديل إعدادات التكلفة", "تعديل سعر اللوح وأجرة القص وإعادة حساب التكلفة.", "critical"),
    Capability.EDIT_SPECIAL_PRICE: _presentation("تعديل سعر معتمد", "تغيير سعر درفة خاصة بعد اعتماده سابقًا.", "critical"),
    Capability.APPROVE_SPECIAL_PRICE: _presentation("اعتماد سعر خاص", "اعتماد السعر النهائي للدرف الخاصة.", "critical"),
    Capability.EDIT_REPLACEMENT_COST: _presentation("تعديل خسارة التعويض", "إدخال التكلفة الفعلية الداخلية عند إكمال قطعة التعويض.", "critical"),
    Capability.PRINT_MEASUREMENTS: _presentation("طباعة القياسات", "طباعة مستند القياسات دون أي أسعار."),
    Capability.PRINT_CUSTOMER_INVOICE: _presentation("طباعة فاتورة الزبون", "طباعة مستند الزبون المالي دون البيانات الداخلية.", "sensitive"),
    Capability.PRINT_INTERNAL_COST_REPORT: _presentation("طباعة تقرير التكلفة الداخلي", "طباعة التقرير السري الذي يتضمن التكلفة والخسائر والربحية.", "critical"),
    Capability.VIEW_CUTTING_PLAN: _presentation("عرض قسم خطة القص", "إظهار تبويب نتائج القص. امنح صلاحيات التبويبات أدناه لتحديد أي خطط يمكن مشاهدتها."),
    Capability.VIEW_SYSTEM_CUTTING_PLAN: _presentation("عرض خطة النظام", "مشاهدة تبويب خطة القص المحسوبة بواسطة النظام."),
    Capability.VIEW_UPLOADED_CUTTING_PLAN: _presentation("عرض الخطة المرفوعة", "مشاهدة تبويب خطة القص المرفوعة (DXF/مخصصة)."),
    Capability.VIEW_APPROVED_CUTTING_PLAN: _presentation("عرض الخطة المعتمدة", "مشاهدة تبويب الخطة المعتمدة للإنتاج."),
    Capability.RECALCULATE_PLAN: _presentation("إعادة حساب الخطة", "إعادة تشغيل محرك توزيع القطع على الألواح.", "sensitive"),
    Capability.EDIT_OPTIMIZER_SETTINGS: _presentation(
        "تعديل خوارزمية القص",
        "تغيير خوارزمية القص التي يقدمها النظام والهوامش وKerf وإعدادات البحث، ثم إعادة الحساب ومشاهدة النتيجة في «خطة النظام». صلاحية مستقلة تمامًا عن «تعديل الطلب»: من يملك تعديل الطلب لا يستطيع تغيير الخوارزمية بدونها.",
        "sensitive",
    ),
    Capability.PRINT_CUTTING_PLAN: _presentation("طباعة خطة القص", "طباعة الخطة المصرح بعرضها."),
    Capability.APPROVE_DXF: _presentation("اعتماد خطة القص", "اعتماد خطة النظام الحالية أو خطة DXF المرفوعة كمصدر نهائي للإنتاج بعد مراجعتها.", "critical"),
    Capability.VIEW_DRAWING_WORKSPACE: _presentation("فتح مساحة الرسم", "عرض أدوات الرسم الخاصة وخطة DXF."),
    Capability.EDIT_SPECIAL_DRAWING: _presentation("تعديل الرسم الخاص", "تحرير هندسة وملاحظات الدرف الخاصة.", "sensitive"),
    Capability.EXPORT_DXF: _presentation("تصدير DXF", "تصدير رسم الإنتاج بصيغة DXF.", "sensitive"),
    Capability.UPLOAD_DXF: _presentation("رفع خطة قص DXF", "رفع خطة قص كملف DXF مع التحقق قبل اعتمادها. مخصصة لعامل الرسم.", "sensitive"),
    Capability.REPLACE_DXF: _presentation("استبدال خطة قص DXF", "استبدال ملف DXF المرفوع سابقًا بعد التحقق. مخصصة لعامل الرسم.", "critical"),
    Capability.DISPATCH_ORDER: _presentation("إرسال الطلب للإنتاج", "اختيار مسار الإنتاج والعامل الأول وإنشاء المراحل."),
    Capability.START_ASSIGNED_STAGE: _presentation("بدء المرحلة المسندة", "بدء المرحلة الحالية عندما تكون مسندة للمستخدم نفسه."),
    Capability.HANDOFF_ASSIGNED_STAGE: _presentation("تسليم المرحلة المسندة", "إنهاء المرحلة وإرسال الطلب إلى العامل التالي."),
    Capability.REVERT_DEPARTMENT: _presentation("إرجاع الطلب لقسم سابق", "إعادة الطلب إلى مرحلة أو قسم سابق مع سجل تدقيق.", "critical"),
    Capability.RETURN_ORDER_TO_DRAFT: _presentation("إعادة الطلب للمسودة", "إعادة نفس الطلب إلى المسودة بعد إلغاء مراحل الإنتاج النشطة، دون إنشاء نسخة جديدة.", "critical"),
    Capability.MARK_DELIVERED: _presentation("تأكيد التسليم", "تغيير حالة الطلب إلى تم التسليم.", "critical"),
    Capability.REASSIGN_WORKER: _presentation("تغيير العامل", "إعادة إسناد المرحلة الحالية إلى عامل مؤهل آخر.", "sensitive"),
    Capability.VIEW_SHOP_FLOOR_HISTORY: _presentation(
        "عرض سجل صالة الإنتاج",
        "عرض الطلبات المنتهية التي تقع أصلًا ضمن نطاق المستخدم. لا تمنح دخول صالة الإنتاج ولا أي إجراء أو نطاق طلبات إضافي.",
    ),
    Capability.ARCHIVE_APPROVED_PLAN: _presentation("أرشفة الخطة المعتمدة", "إنشاء وحفظ PDF رسمي خاص بالخطة المعتمدة.", "sensitive"),
    Capability.VIEW_PRODUCTION_INCIDENTS: _presentation("عرض أخطاء الإنتاج", "عرض قائمة حوادث وأخطاء الإنتاج المسجلة ومتابعة تفاصيلها."),
    Capability.RECORD_INCIDENT: _presentation("تسجيل حادث إنتاج", "تسجيل قطعة متضررة أو مشكلة أثناء التنفيذ.", "sensitive"),
    Capability.CREATE_REPLACEMENT: _presentation("إنشاء قطعة تعويض", "إنشاء قطعة تعويض من حادث إنتاج مسجل.", "sensitive"),
    Capability.VIEW_REPLACEMENTS: _presentation("عرض قطع التعويض", "فتح قطع التعويض ومتابعة حالتها."),
    Capability.APPROVE_REPLACEMENT: _presentation("اعتماد قطعة التعويض", "اعتماد القطعة وإنشاء خطة القص المصغرة وتجميد تكلفتها المتوقعة.", "critical"),
    Capability.START_REPLACEMENT: _presentation("بدء قطعة التعويض", "بدء تنفيذ قطعة تعويض معتمدة."),
    Capability.COMPLETE_REPLACEMENT: _presentation("إكمال قطعة التعويض", "إنهاء قطعة التعويض وتحديث حالة الطلب."),
    Capability.CANCEL_REPLACEMENT: _presentation("إلغاء قطعة التعويض", "إلغاء قطعة تعويض لم يبدأ تنفيذها بعد.", "critical"),
    Capability.VIEW_OPERATIONAL_REPORTS: _presentation("عرض التقارير التشغيلية", "عرض الأداء والمراحل والحوادث دون التكلفة والخسائر المالية.", "sensitive"),
    Capability.VIEW_FINANCIAL_REPORTS: _presentation("عرض التقارير المالية الداخلية", "عرض التكلفة الفعلية والهدر والخسائر الداخلية داخل التقارير.", "critical"),
    Capability.VIEW_USERS: _presentation("عرض مستخدمي المعمل", "عرض حسابات Almdina فقط وحالتها والأدوار المسندة لها."),
    Capability.CREATE_USERS: _presentation("إنشاء مستخدم", "إنشاء حساب نظام جديد للمعمل مع كلمة مرور مؤقتة.", "critical"),
    Capability.EDIT_USERS: _presentation("تعديل بيانات المستخدم", "تعديل الاسم واللغة وبيانات الحساب غير المالية.", "sensitive"),
    Capability.ASSIGN_USER_ROLES: _presentation("إسناد الأدوار للمستخدم", "إضافة أو إزالة أدوار النظام من حساب مستخدم Almdina.", "critical"),
    Capability.ENABLE_USERS: _presentation("تفعيل المستخدم", "إعادة تفعيل حساب معمل معطّل.", "critical"),
    Capability.DISABLE_USERS: _presentation("تعطيل المستخدم", "تعطيل حساب بعد التأكد من عدم وجود مراحل إنتاج نشطة.", "critical"),
    Capability.RESET_USER_PASSWORD: _presentation("إعادة كلمة المرور", "تعيين كلمة مرور مؤقتة جديدة دون إظهارها أو تخزينها في السجل.", "critical"),
    Capability.VIEW_FACTORY_SETTINGS: _presentation("عرض إعدادات المعمل", "عرض إعدادات القص والتكلفة وضوابط الإنتاج وهوية أوراق الطباعة دون تعديل."),
    Capability.EDIT_FACTORY_CUTTING_DEFAULTS: _presentation("تعديل افتراضيات القص", "تعديل Kerf والهامش والخوارزمية ونوع الآلة وحدود البحث.", "sensitive"),
    Capability.EDIT_FACTORY_COST_DEFAULTS: _presentation("تعديل افتراضيات التكلفة", "تعديل أجرة القص ورسوم الدرف الخاصة وهوامشها.", "critical"),
    Capability.EDIT_FACTORY_PRODUCTION_CONTROLS: _presentation("تعديل ضوابط الإنتاج", "تعديل المسار الافتراضي والاستثناءات التشغيلية الحساسة.", "critical"),
    Capability.EDIT_FACTORY_PRINT_IDENTITY: _presentation("تعديل هوية الطباعة", "تعديل اسم المعمل ولمحته وعنوانه وأرقام التواصل الظاهرة على أوراق الطباعة.", "sensitive"),
    Capability.VIEW_PRODUCTION_ROUTINGS: _presentation("عرض مسارات الإنتاج", "عرض مسارات الإنتاج وتسلسل مراحلها."),
    Capability.CREATE_PRODUCTION_ROUTINGS: _presentation("إنشاء مسار إنتاج", "إنشاء مسار إنتاج جديد.", "sensitive"),
    Capability.EDIT_PRODUCTION_ROUTINGS: _presentation("تعديل مسارات الإنتاج", "تعديل ترتيب المراحل أو تعطيل المسار.", "critical"),
    Capability.DELETE_PRODUCTION_ROUTINGS: _presentation("حذف مسار إنتاج", "حذف مسار غير مستخدم وغير معيّن كافتراضي.", "critical"),
    Capability.VIEW_EDGE_BANDING_TYPES: _presentation("عرض أنواع القشاط", "عرض أنواع القشاط والسماكة والسعر والحالة."),
    Capability.CREATE_EDGE_BANDING_TYPES: _presentation("إنشاء نوع قشاط", "إضافة نوع قشاط جديد.", "sensitive"),
    Capability.EDIT_EDGE_BANDING_TYPES: _presentation("تعديل أنواع القشاط", "تعديل السماكة والسعر والخصائص أو تعطيل النوع.", "critical"),
    Capability.DELETE_EDGE_BANDING_TYPES: _presentation("حذف نوع قشاط", "حذف نوع غير مستخدم في أي طلب أو قطعة.", "critical"),
    Capability.VIEW_CUSTOMERS: _presentation("عرض الزبائن", "عرض قائمة الزبائن وإدارتها من مساحة البيانات الأساسية، واختيار الزبون في الطلبات."),
    Capability.CREATE_CUSTOMERS: _presentation("إنشاء زبون", "إضافة زبون جديد من قائمة الزبائن أو من حقل الاختيار في الطلب.", "sensitive"),
    Capability.EDIT_CUSTOMERS: _presentation("تعديل الزبائن", "تعديل بيانات الزبون الحالية.", "sensitive"),
    Capability.DELETE_CUSTOMERS: _presentation("حذف زبون", "حذف زبون غير مرتبط بطلبات محفوظة.", "critical"),
    Capability.MANAGE_PERMISSIONS: _presentation("إدارة الصلاحيات", "تعديل مصفوفة الصلاحيات لجميع الأدوار.", "critical"),
}

_REPLACEMENT_ACTIONS = frozenset({
    Capability.APPROVE_REPLACEMENT,
    Capability.START_REPLACEMENT,
    Capability.COMPLETE_REPLACEMENT,
    Capability.CANCEL_REPLACEMENT,
    Capability.EDIT_REPLACEMENT_COST,
})
_COST_VIEW_ACTIONS = frozenset({
    Capability.EDIT_COST_SETTINGS,
    Capability.EDIT_SPECIAL_PRICE,
    Capability.APPROVE_SPECIAL_PRICE,
    Capability.PRINT_INTERNAL_COST_REPORT,
})
_PLAN_VIEW_ACTIONS = frozenset({
    Capability.RECALCULATE_PLAN,
    Capability.EDIT_OPTIMIZER_SETTINGS,
    Capability.PRINT_CUTTING_PLAN,
    Capability.APPROVE_DXF,
})
_PLAN_TAB_VIEW_ACTIONS = frozenset({
    Capability.VIEW_SYSTEM_CUTTING_PLAN,
    Capability.VIEW_UPLOADED_CUTTING_PLAN,
    Capability.VIEW_APPROVED_CUTTING_PLAN,
})
_DRAWING_VIEW_ACTIONS = frozenset({
    Capability.EDIT_SPECIAL_DRAWING,
    Capability.EXPORT_DXF,
    Capability.UPLOAD_DXF,
    Capability.REPLACE_DXF,
})
_WORKFORCE_ACTIONS = frozenset(WORKFORCE_CAPABILITIES.difference({Capability.VIEW_USERS}))
_FACTORY_SECTION_EDITS = frozenset(FACTORY_SETTINGS_CAPABILITIES.difference({Capability.VIEW_FACTORY_SETTINGS}))
_ROUTING_ACTIONS = frozenset({
    Capability.CREATE_PRODUCTION_ROUTINGS,
    Capability.EDIT_PRODUCTION_ROUTINGS,
    Capability.DELETE_PRODUCTION_ROUTINGS,
})
_EDGE_ACTIONS = frozenset({
    Capability.CREATE_EDGE_BANDING_TYPES,
    Capability.EDIT_EDGE_BANDING_TYPES,
    Capability.DELETE_EDGE_BANDING_TYPES,
})
_CUSTOMER_ACTIONS = frozenset({
    Capability.CREATE_CUSTOMERS,
    Capability.EDIT_CUSTOMERS,
    Capability.DELETE_CUSTOMERS,
})
_ORDER_INPUT_ACTIONS = frozenset({
    Capability.CREATE_ORDER,
    Capability.EDIT_ORDER,
    Capability.CREATE_ORDER_REVISION,
})


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
    if state[Capability.EDIT_OPTIMIZER_SETTINGS]:
        state[Capability.RECALCULATE_PLAN] = True
    if state[Capability.RECALCULATE_PLAN]:
        state[Capability.VIEW_SYSTEM_CUTTING_PLAN] = True

    # History is read-only Shop Floor visibility. It is deliberately excluded
    # from transactional dependencies so granting it alone cannot promote
    # VIEW_ORDERS or widen native Door Cutting Order scope.
    transactional_actions = {
        capability
        for capability, enabled in state.items()
        if enabled
        and CAPABILITY_CATALOG[capability].applies_to in {"Door Cutting Order", CUTTING_PLAN_DOCTYPE}
        and capability not in {
            Capability.VIEW_ORDERS,
            Capability.VIEW_SHOP_FLOOR_HISTORY,
        }
    }
    if transactional_actions:
        state[Capability.VIEW_ORDERS] = True
    if any(state[capability] for capability in _COST_VIEW_ACTIONS):
        state[Capability.VIEW_COSTS] = True
    if any(state[capability] for capability in _PLAN_VIEW_ACTIONS):
        state[Capability.VIEW_CUTTING_PLAN] = True
    if any(state[capability] for capability in _PLAN_TAB_VIEW_ACTIONS):
        state[Capability.VIEW_CUTTING_PLAN] = True
    if any(state[capability] for capability in _DRAWING_VIEW_ACTIONS):
        state[Capability.VIEW_DRAWING_WORKSPACE] = True
    if any(state[capability] for capability in _REPLACEMENT_ACTIONS):
        state[Capability.VIEW_REPLACEMENTS] = True
    if state[Capability.ARCHIVE_APPROVED_PLAN]:
        state[Capability.VIEW_CUTTING_PLAN] = True
        state[Capability.VIEW_APPROVED_CUTTING_PLAN] = True
        state[Capability.PRINT_CUTTING_PLAN] = True
    if state[Capability.VIEW_CUTTING_PLAN]:
        granular_supplied = any(key in supplied for key in _PLAN_TAB_VIEW_ACTIONS)
        if not granular_supplied:
            for capability in _PLAN_TAB_VIEW_ACTIONS:
                state[capability] = True
        elif not any(state[capability] for capability in _PLAN_TAB_VIEW_ACTIONS):
            state[Capability.VIEW_SYSTEM_CUTTING_PLAN] = True
    if state[Capability.VIEW_FINANCIAL_REPORTS]:
        state[Capability.VIEW_OPERATIONAL_REPORTS] = True
        state[Capability.VIEW_COSTS] = True
    if any(state[capability] for capability in _WORKFORCE_ACTIONS):
        state[Capability.VIEW_USERS] = True
    if any(state[capability] for capability in _FACTORY_SECTION_EDITS):
        state[Capability.VIEW_FACTORY_SETTINGS] = True
    if state[Capability.EDIT_FACTORY_PRODUCTION_CONTROLS]:
        state[Capability.VIEW_PRODUCTION_ROUTINGS] = True
    if any(state[capability] for capability in _ROUTING_ACTIONS):
        state[Capability.VIEW_PRODUCTION_ROUTINGS] = True
    if any(state[capability] for capability in _EDGE_ACTIONS):
        state[Capability.VIEW_EDGE_BANDING_TYPES] = True
    if any(state[capability] for capability in _CUSTOMER_ACTIONS):
        state[Capability.VIEW_CUSTOMERS] = True
    if any(state[capability] for capability in _ORDER_INPUT_ACTIONS):
        state[Capability.VIEW_CUSTOMERS] = True
        state[Capability.VIEW_EDGE_BANDING_TYPES] = True
    return state


def standard_permission_projection(
    doctype: str,
    state: Mapping[str, Any] | None,
) -> dict[str, bool]:
    """Project business grants onto standard Frappe permission columns."""

    normalized = normalize_capability_state(state)
    if doctype == "Door Cutting Order":
        can_read = normalized[Capability.VIEW_ORDERS]
        return {
            "read": can_read,
            "select": can_read,
            "create": normalized[Capability.CREATE_ORDER],
            "write": normalized[Capability.EDIT_ORDER],
            "delete": False,
        }
    if doctype == CUTTING_PLAN_DOCTYPE:
        can_read = normalized[Capability.VIEW_CUTTING_PLAN]
        return {
            "read": can_read,
            "select": can_read,
            "create": False,
            "write": False,
            "delete": False,
        }
    if doctype == "Almdina ERP Settings":
        can_read_settings = (
            normalized[Capability.VIEW_FACTORY_SETTINGS]
            or any(normalized[value] for value in _FACTORY_SECTION_EDITS)
        )
        return {"read": can_read_settings, "select": can_read_settings, "create": False, "write": False, "delete": False}
    if doctype == "Replacement Piece":
        enabled = any(
            normalized[capability]
            for capability, definition in CAPABILITY_CATALOG.items()
            if definition.applies_to == doctype
        )
        return {"read": enabled, "select": enabled, "create": False, "write": False, "delete": False}
    if doctype == "Production Incident":
        can_read = normalized[Capability.VIEW_PRODUCTION_INCIDENTS]
        return {"read": can_read, "select": can_read, "create": False, "write": False, "delete": False}
    if doctype == "Production Routing":
        can_read = normalized[Capability.VIEW_PRODUCTION_ROUTINGS]
        return {"read": can_read, "select": can_read, "create": normalized[Capability.CREATE_PRODUCTION_ROUTINGS], "write": normalized[Capability.EDIT_PRODUCTION_ROUTINGS], "delete": normalized[Capability.DELETE_PRODUCTION_ROUTINGS]}
    if doctype == "Customer":
        can_read = normalized[Capability.VIEW_CUSTOMERS]
        return {"read": can_read, "select": can_read, "create": normalized[Capability.CREATE_CUSTOMERS], "write": normalized[Capability.EDIT_CUSTOMERS], "delete": normalized[Capability.DELETE_CUSTOMERS]}
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
    """Project sensitive cost visibility while keeping all edits command-owned."""

    normalized = normalize_capability_state(state)
    if doctype not in {"Door Cutting Order", CUTTING_PLAN_DOCTYPE}:
        return {}
    return {
        1: {
            "read": normalized[Capability.VIEW_COSTS],
            "write": False,
        }
    }


def enabled_capabilities(state: Mapping[str, Any] | None) -> frozenset[str]:
    normalized = normalize_capability_state(state)
    return normalize_capabilities(
        capability
        for capability, enabled in normalized.items()
        if enabled
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
    "CAPABILITY_PRESENTATION",
    "CATEGORY_ORDER",
    "CATEGORY_PRESENTATION",
    "capability_catalog_payload",
    "changed_capabilities",
    "enabled_capabilities",
    "field_permission_projection",
    "normalize_capability_state",
    "permission_impact",
    "standard_permission_projection",
]
