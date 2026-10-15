(() => {
    "use strict";

    if (window.AlmdinaShortcutPresentation) return;

    const REPORTS_SECTION_ICON = "es-line-reports";

    /**
     * Stable presentation keyed by Frappe link_to / route / DocType name.
     * label and desc are English message IDs. Translate them at render time.
     */
    const SHORTCUT_BY_LINK_TO = Object.freeze({
        Customer: {
            label: "Customers",
            desc: "Manage customer records and contact details",
            icon: "users",
        },
        "Edge Banding Type": {
            label: "Edge banding types and prices",
            desc: "Define edge banding types and their prices and thicknesses",
            icon: "tool",
        },
        "factory-production-settings": {
            label: "Factory Settings",
            desc: "Default production and cutting settings",
            icon: "setting",
        },
        Role: {
            label: "Role management",
            desc: "Frappe roles used in the factory",
            icon: "shield",
        },
        "factory-permissions": {
            label: "Permission management",
            desc: "Almdina permission matrix by role",
            icon: "lock",
        },
        "factory-workforce": {
            label: "User management",
            desc: "Factory accounts, roles, and entry pages",
            icon: "hr",
        },
        "factory-master-data": {
            label: "Production route management",
            desc: "Production routes and operational stages",
            icon: "branch",
        },
        "Door Cutting Order": {
            label: "Door cutting orders",
            desc: "Create and follow cutting orders",
            icon: "clipboard",
        },
        "shop-floor-inbox": {
            label: "Production stages",
            desc: "Shop floor board and inbox",
            icon: "organization",
        },
        "Replacement Part": {
            label: "Replacement parts",
            desc: "Replacement parts linked to production errors",
            icon: "duplicate",
        },
        "Production Error": {
            label: "Production errors",
            desc: "Record and follow production incidents",
            icon: "close",
        },
        "Factory Operations Summary": {
            label: "Factory operations summary",
            desc: "Overview of factory activity",
            icon: "es-line-chart",
        },
        "Cutting Order Analysis": {
            label: "Cutting order analysis",
            desc: "Order and performance analysis",
            icon: "es-line-reports",
        },
        "Board Usage Analysis": {
            label: "Board usage analysis",
            desc: "Board consumption and waste",
            icon: "table",
        },
        "Door Measurement Analysis": {
            label: "Door measurement analysis",
            desc: "Most used measurements",
            icon: "small-file",
        },
        "Production Stage Performance": {
            label: "Production stage performance",
            desc: "Stage time and productivity",
            icon: "timer",
        },
        "Production Errors and Replacement Parts": {
            label: "Production errors and replacement parts",
            desc: "Combined incident and compensation report",
            icon: "es-line-reports",
        },
    });

    /**
     * Label → link_to bridge for widgets that only expose a stored shortcut name.
     * Arabic keys are legacy compatibility. They are not the displayed text.
     */
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
        Customers: "Customer",
        "Edge banding types and prices": "Edge Banding Type",
        "Factory Settings": "factory-production-settings",
        "Role management": "Role",
        "Permission management": "factory-permissions",
        "User management": "factory-workforce",
        "Production route management": "factory-master-data",
        "Door cutting orders": "Door Cutting Order",
        "Production stages": "shop-floor-inbox",
        "Replacement parts": "Replacement Part",
        "Production errors": "Production Error",
        "Factory operations summary": "Factory Operations Summary",
        "Cutting order analysis": "Cutting Order Analysis",
        "Board usage analysis": "Board Usage Analysis",
        "Door measurement analysis": "Door Measurement Analysis",
        "Production stage performance": "Production Stage Performance",
        "Production errors and replacement parts": "Production Errors and Replacement Parts",
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

    function linkRouteKey(value) {
        return normalizeText(value).toLowerCase().replace(/\s+/g, "-");
    }

    const LINK_TO_BY_ROUTE_KEY = Object.freeze(
        Object.fromEntries(
            Object.keys(SHORTCUT_BY_LINK_TO).map((key) => [linkRouteKey(key), key])
        )
    );

    function canonicalLinkTo(linkTo) {
        const key = normalizeText(linkTo);
        if (!key) return "";
        if (SHORTCUT_BY_LINK_TO[key]) return key;
        const routed = LINK_TO_BY_ROUTE_KEY[linkRouteKey(key)];
        if (routed && SHORTCUT_BY_LINK_TO[routed]) return routed;
        if (LABEL_TO_LINK_TO[key] && SHORTCUT_BY_LINK_TO[LABEL_TO_LINK_TO[key]]) {
            return LABEL_TO_LINK_TO[key];
        }
        return "";
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
        const canonical = canonicalLinkTo(linkTo);
        if (canonical) return SHORTCUT_BY_LINK_TO[canonical];
        const key = normalizeText(linkTo);
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
