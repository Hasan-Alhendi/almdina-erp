(() => {
    "use strict";

    if (window.AlmdinaShortcutPresentation) return;

    const REPORTS_SECTION_ICON = "es-line-reports";

    /**
     * Stable presentation keyed by Frappe link_to / route / DocType name.
     * Prefer metaForLinkTo / metaForRoute over visible Arabic labels.
     */
    const SHORTCUT_BY_LINK_TO = Object.freeze({
        Customer: { desc: "إدارة سجلات الزبائن وبيانات التواصل", icon: "users" },
        "Edge Banding Type": { desc: "تعريف أنواع القشاط والأسعار والسماكات", icon: "tool" },
        "factory-production-settings": { desc: "إعدادات الإنتاج والقص الافتراضية", icon: "setting" },
        Role: { desc: "أدوار Frappe المستخدمة في المعمل", icon: "shield" },
        "factory-permissions": { desc: "مصفوفة صلاحيات Almdina حسب الدور", icon: "lock" },
        "factory-workforce": { desc: "حسابات المعمل والأدوار وصفحات الدخول", icon: "hr" },
        "factory-master-data": { desc: "مسارات الإنتاج والمراحل التشغيلية", icon: "branch" },
        "Door Cutting Order": { desc: "إنشاء ومتابعة طلبات القص", icon: "clipboard" },
        "shop-floor-inbox": { desc: "لوحة التشغيل وصندوق الوارد", icon: "organization" },
        "Replacement Part": { desc: "قطع بديلة مرتبطة بأخطاء الإنتاج", icon: "duplicate" },
        "Production Error": { desc: "تسجيل ومتابعة حوادث الإنتاج", icon: "close" },
        "Factory Operations Summary": { desc: "نظرة عامة على حركة المعمل", icon: "es-line-chart" },
        "Cutting Order Analysis": { desc: "تحليل الطلبات والأداء", icon: "es-line-reports" },
        "Board Usage Analysis": { desc: "استهلاك الألواح والهدر", icon: "table" },
        "Door Measurement Analysis": { desc: "أكثر المقاسات استخدامًا", icon: "small-file" },
        "Production Stage Performance": { desc: "زمن المراحل والإنتاجية", icon: "timer" },
        "Production Errors and Replacement Parts": {
            desc: "تقرير موحد للحوادث والتعويض",
            icon: "es-line-reports",
        },
    });

    /** Label → link_to bridge for Frappe widgets that only expose the shortcut label. */
    const LABEL_TO_LINK_TO = Object.freeze({
        "الزبائن": "Customer",
        "أنواع القشاط وأسعاره": "Edge Banding Type",
        "إعدادات المعمل": "factory-production-settings",
        "إدارة الأدوار": "Role",
        "إدارة الصلاحيات": "factory-permissions",
        "إدارة المستخدمين": "factory-workforce",
        "إدارة مسارات الإنتاج": "factory-master-data",
        "طلبات قص الدرف": "Door Cutting Order",
        "مراحل الإنتاج": "shop-floor-inbox",
        "القطع التعويضية": "Replacement Part",
        "أخطاء الإنتاج": "Production Error",
        "ملخص عمليات المعمل": "Factory Operations Summary",
        "تحليل طلبات القص": "Cutting Order Analysis",
        "تحليل استخدام الألواح": "Board Usage Analysis",
        "تحليل قياسات الدرف": "Door Measurement Analysis",
        "أداء مراحل الإنتاج": "Production Stage Performance",
        "أخطاء الإنتاج والقطع التعويضية": "Production Errors and Replacement Parts",
    });

    /** Compatibility surface: label → presentation (derived from link_to catalog). */
    const SHORTCUT_PRESENTATION = Object.freeze(
        Object.fromEntries(
            Object.entries(LABEL_TO_LINK_TO).map(([label, linkTo]) => [
                label,
                SHORTCUT_BY_LINK_TO[linkTo],
            ])
        )
    );

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
        "factory-workforce": "hr",
        "factory-permissions": "lock",
        "factory-production-settings": "setting",
        "factory-master-data": "branch",
    });

    function normalizeText(value) {
        return String(value || "").replace(/\s+/g, " ").trim();
    }

    function normalizeRoute(value) {
        const text = normalizeText(value);
        if (!text) return "";
        try {
            const url = new URL(text, window.location.origin);
            const parts = url.pathname.split("/").filter(Boolean);
            // /app/<route> or /desk/<route>
            if (parts.length >= 2 && (parts[0] === "app" || parts[0] === "desk")) {
                return parts.slice(1).join("/");
            }
            return parts[parts.length - 1] || text;
        } catch (_error) {
            return text.replace(/^#\/?/, "").split("?")[0];
        }
    }

    function metaForLinkTo(linkTo) {
        const key = normalizeText(linkTo);
        if (!key) return null;
        if (SHORTCUT_BY_LINK_TO[key]) return SHORTCUT_BY_LINK_TO[key];
        const aliasIcon = LABEL_ICON_ALIASES[key];
        if (aliasIcon) return Object.freeze({ desc: "", icon: aliasIcon });
        return null;
    }

    function metaForRoute(route) {
        const normalized = normalizeRoute(route);
        if (!normalized) return null;
        const direct = metaForLinkTo(normalized);
        if (direct) return direct;
        // List/Form routes: List/Door Cutting Order → Door Cutting Order
        const segments = normalized.split("/").filter(Boolean);
        if (segments.length >= 2) {
            return metaForLinkTo(segments[segments.length - 1])
                || metaForLinkTo(segments[1]);
        }
        return null;
    }

    function linkToForLabel(label) {
        const normalized = normalizeText(label);
        if (!normalized) return "";
        if (LABEL_TO_LINK_TO[normalized]) return LABEL_TO_LINK_TO[normalized];
        const key = Object.keys(LABEL_TO_LINK_TO).find(
            (candidate) => normalized.includes(candidate) || candidate.includes(normalized)
        );
        return key ? LABEL_TO_LINK_TO[key] : "";
    }

    function metaForLabel(label) {
        const linkTo = linkToForLabel(label);
        if (linkTo) return metaForLinkTo(linkTo);
        const normalized = normalizeText(label);
        if (!normalized) return null;
        if (SHORTCUT_PRESENTATION[normalized]) return SHORTCUT_PRESENTATION[normalized];
        const aliasIcon = LABEL_ICON_ALIASES[normalized];
        if (aliasIcon) return Object.freeze({ desc: "", icon: aliasIcon });
        return null;
    }

    function iconForLabel(label, options = {}) {
        const meta = metaForLabel(label) || metaForLinkTo(label) || metaForRoute(label);
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
        SHORTCUT_BY_LINK_TO,
        LABEL_TO_LINK_TO,
        SHORTCUT_PRESENTATION,
        LABEL_ICON_ALIASES,
        normalizeText,
        normalizeRoute,
        metaForLinkTo,
        metaForRoute,
        metaForLabel,
        linkToForLabel,
        iconForLabel,
        renderIcon,
    });
})();
