(() => {
    "use strict";

    if (window.AlmdinaShortcutPresentation) return;

    const REPORTS_SECTION_ICON = "es-line-reports";

    const SHORTCUT_PRESENTATION = Object.freeze({
        "الزبائن": { desc: "إدارة سجلات الزبائن وبيانات التواصل", icon: "users" },
        "أنواع القشاط وأسعاره": { desc: "تعريف أنواع القشاط والأسعار والسماكات", icon: "tool" },
        "إعدادات المعمل": { desc: "إعدادات الإنتاج والقص الافتراضية", icon: "setting" },
        "إدارة الأدوار": { desc: "أدوار Frappe المستخدمة في المعمل", icon: "shield" },
        "إدارة الصلاحيات": { desc: "مصفوفة صلاحيات Almdina حسب الدور", icon: "lock" },
        "إدارة المستخدمين": { desc: "حسابات المعمل والأدوار وصفحات الدخول", icon: "hr" },
        "إدارة مسارات الإنتاج": { desc: "مسارات الإنتاج والمراحل التشغيلية", icon: "branch" },
        "طلبات قص الدرف": { desc: "إنشاء ومتابعة طلبات القص", icon: "clipboard" },
        "مراحل الإنتاج": { desc: "لوحة التشغيل وصندوق الوارد", icon: "organization" },
        "القطع التعويضية": { desc: "قطع بديلة مرتبطة بأخطاء الإنتاج", icon: "duplicate" },
        "أخطاء الإنتاج": { desc: "تسجيل ومتابعة حوادث الإنتاج", icon: "close" },
        "ملخص عمليات المعمل": { desc: "نظرة عامة على حركة المعمل", icon: "es-line-chart" },
        "تحليل طلبات القص": { desc: "تحليل الطلبات والأداء", icon: "es-line-reports" },
        "تحليل استخدام الألواح": { desc: "استهلاك الألواح والهدر", icon: "table" },
        "تحليل قياسات الدرف": { desc: "أكثر المقاسات استخدامًا", icon: "small-file" },
        "أداء مراحل الإنتاج": { desc: "زمن المراحل والإنتاجية", icon: "timer" },
        "أخطاء الإنتاج والقطع التعويضية": {
            desc: "تقرير موحد للحوادث والتعويض",
            icon: "es-line-reports",
        },
    });

    const LABEL_ICON_ALIASES = Object.freeze({
        "الرئيسية": "home",
        Home: "home",
        "إدارة المعمل": "tool",
        "Almdina ERP": "tool",
        Customers: "users",
        Customer: "users",
        "Edge Banding Types": "tool",
        "Edge Banding Type": "tool",
        "Factory Settings": "setting",
        "Role Management": "shield",
        Role: "shield",
        "Permission Management": "lock",
        Permissions: "lock",
        "User Management": "hr",
        Workforce: "hr",
        "Production Routing": "branch",
        "Factory Master Data": "branch",
        "Door Cutting Orders": "clipboard",
        "Door Cutting Order": "clipboard",
        "Production Orders": "clipboard",
        "Production Stages": "organization",
        "Shop Floor": "organization",
        "shop-floor-inbox": "organization",
        "Replacement Parts": "duplicate",
        "Production Errors": "close",
        "Production Error": "close",
        "Factory Operations Summary": "es-line-chart",
        "Cutting Order Analysis": "es-line-reports",
        "Board Usage Analysis": "table",
        "Door Measurement Analysis": "small-file",
        "Production Stage Performance": "timer",
    });

    function normalizeText(value) {
        return String(value || "").replace(/\s+/g, " ").trim();
    }

    function metaForLabel(label) {
        const normalized = normalizeText(label);
        if (!normalized) return null;
        if (SHORTCUT_PRESENTATION[normalized]) return SHORTCUT_PRESENTATION[normalized];
        const key = Object.keys(SHORTCUT_PRESENTATION).find(
            (candidate) => normalized.includes(candidate) || candidate.includes(normalized)
        );
        if (key) return SHORTCUT_PRESENTATION[key];
        const aliasIcon = LABEL_ICON_ALIASES[normalized];
        if (aliasIcon) return Object.freeze({ desc: "", icon: aliasIcon });
        return null;
    }

    function iconForLabel(label, options = {}) {
        const meta = metaForLabel(label);
        if (!meta) return null;
        if (options && options.reportsSection) return meta.icon || REPORTS_SECTION_ICON;
        return meta.icon;
    }

    function renderIcon(name, size = "md") {
        if (window.frappe && frappe.utils && typeof frappe.utils.icon === "function") {
            return frappe.utils.icon(name, size, "", "", "current-color", true);
        }
        return "";
    }

    window.AlmdinaShortcutPresentation = Object.freeze({
        REPORTS_SECTION_ICON,
        SHORTCUT_PRESENTATION,
        LABEL_ICON_ALIASES,
        normalizeText,
        metaForLabel,
        iconForLabel,
        renderIcon,
    });
})();
