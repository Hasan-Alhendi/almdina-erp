(() => {
    "use strict";

    if (window.__almdinaPermissionActionVisibilityGuard) return;
    window.__almdinaPermissionActionVisibilityGuard = true;

    /*
     * Frappe v16 does not consistently expose a route/link_to attribute on
     * rendered Workspace shortcuts or persistent sidebar entries. In those
     * cases it exposes only the configured Workspace label (often through
     * data-widget-name/data-name or visible text). Keep this bridge explicit:
     * labels identify UI widgets, while the server-provided surface flag stays
     * the sole authorization decision.
     */
    const WORKSPACE_LABEL_SURFACES = Object.freeze({
        "أنواع القشاط وأسعاره": "edge_banding_types",
        "الزبائن": "customer_admin",
        "إعدادات المعمل": "factory_settings",
        "إدارة الأدوار": "role_admin",
        "إدارة الصلاحيات": "permissions",
        "إدارة المستخدمين": "workforce",
        "إدارة مسارات الإنتاج": "factory_master_data",
        "طلبات قص الدرف": "orders",
        "مراحل الإنتاج": "production_stages",
        "القطع التعويضية": "replacements",
        "أخطاء الإنتاج": "production_incidents",
        "ملخص عمليات المعمل": "report_factory_operations_summary",
        "تحليل طلبات القص": "report_factory_order_analysis",
        "تحليل استخدام الألواح": "report_board_usage_analysis",
        "تحليل قياسات الدرف": "report_piece_size_usage_analysis",
        "أداء مراحل الإنتاج": "report_production_stage_performance",
        "أخطاء الإنتاج والقطع التعويضية": "report_production_incidents_and_replacements",
    });

    const WORKSPACE_SECTION_SURFACES = Object.freeze({
        "الإعدادات الأساسية": Object.freeze([
            "customer_admin",
            "edge_banding_types",
            "factory_settings",
        ]),
        "إدارة النظام ومسارات العمل": Object.freeze([
            "role_admin",
            "permissions",
            "workforce",
            "factory_master_data",
        ]),
        "التشغيل اليومي": Object.freeze([
            "orders",
            "production_stages",
            "replacements",
            "production_incidents",
        ]),
        "التقارير التشغيلية والتكلفة": Object.freeze([
            "report_factory_operations_summary",
            "report_factory_order_analysis",
            "report_board_usage_analysis",
            "report_piece_size_usage_analysis",
            "report_production_stage_performance",
            "report_production_incidents_and_replacements",
        ]),
    });

    const WORKSPACE_ITEM_SELECTOR = [
        ".shortcut-widget-box",
        ".widget.shortcut-widget-box",
        ".link-item",
        ".workspace-link",
        ".sidebar-item-container",
        ".desk-sidebar-item",
        "[data-widget-name]",
    ].join(", ");

    const WORKSPACE_HEADER_SELECTOR = [
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        ".h4",
        ".widget-group-title",
        ".workspace-section-title",
        "[data-block-type='header']",
    ].join(", ");

    const WORKSPACE_LABELS_LONGEST_FIRST = Object.freeze(
        Object.keys(WORKSPACE_LABEL_SURFACES).sort((left, right) => right.length - left.length)
    );

    let observer = null;
    let timer = null;

    function permissions() {
        return window.AlmdinaPermissions || null;
    }

    function can(capability) {
        const api = permissions();
        return Boolean(api && typeof api.can === "function" && api.can(capability));
    }

    function surfaceAllowed(surface) {
        const api = permissions();
        return Boolean(
            api
            && typeof api.surface === "function"
            && api.surface(String(surface || ""))
        );
    }

    function routeSlug(value) {
        return String(value || "")
            .trim()
            .toLowerCase()
            .replace(/^(app|desk)\//, "")
            .replace(/[^a-z0-9\u0600-\u06ff]+/g, "-")
            .replace(/^-+|-+$/g, "");
    }

    function currentRoute() {
        if (window.frappe && typeof frappe.get_route === "function") {
            const route = frappe.get_route();
            if (Array.isArray(route) && route.length) {
                if (["list", "form", "query-report", "report"].includes(String(route[0] || "").toLowerCase())) {
                    return routeSlug(route[1]);
                }
                return routeSlug(route[0]);
            }
        }
        return routeSlug(window.location.pathname || "");
    }

    function normalizedText(value) {
        return String(value || "").replace(/\s+/g, " ").trim();
    }

    function buttonText(button) {
        return normalizedText(button && button.textContent);
    }

    function setHidden(element, hidden, marker) {
        if (!element || !element.style) return;
        const key = String(marker || "almdinaPermissionActionHidden");
        if (hidden) {
            element.dataset[key] = "1";
            element.style.setProperty("display", "none", "important");
            element.setAttribute("aria-hidden", "true");
            return;
        }
        if (element.dataset[key] === "1") {
            delete element.dataset[key];
            element.style.removeProperty("display");
            element.removeAttribute("aria-hidden");
        }
    }

    function hideButton(button, hidden) {
        if (!button || !button.style) return;
        if (hidden) {
            button.dataset.almdinaPermissionActionHidden = "1";
            button.style.setProperty("display", "none", "important");
            button.setAttribute("aria-hidden", "true");
            button.setAttribute("tabindex", "-1");
            return;
        }
        if (button.dataset.almdinaPermissionActionHidden === "1") {
            delete button.dataset.almdinaPermissionActionHidden;
            button.style.removeProperty("display");
            button.removeAttribute("aria-hidden");
            button.removeAttribute("tabindex");
        }
    }

    function workspaceLabel(element) {
        if (!element) return "";
        const values = [
            element.getAttribute && element.getAttribute("data-widget-name"),
            element.getAttribute && element.getAttribute("data-name"),
            element.getAttribute && element.getAttribute("data-label"),
            element.getAttribute && element.getAttribute("aria-label"),
            element.getAttribute && element.getAttribute("title"),
            element.dataset && element.dataset.widgetName,
            element.dataset && element.dataset.name,
            element.dataset && element.dataset.label,
        ].map(normalizedText).filter(Boolean);

        for (const value of values) {
            if (Object.prototype.hasOwnProperty.call(WORKSPACE_LABEL_SURFACES, value)) {
                return value;
            }
        }

        const visible = normalizedText(element.textContent);
        if (!visible) return "";
        for (const label of WORKSPACE_LABELS_LONGEST_FIRST) {
            if (visible === label || visible.includes(label)) return label;
        }
        return "";
    }

    function workspaceItemContainer(element) {
        if (!element) return null;
        if (typeof element.matches === "function" && element.matches(WORKSPACE_ITEM_SELECTOR)) {
            return element;
        }
        return element.closest && element.closest(WORKSPACE_ITEM_SELECTOR);
    }

    function guardWorkspaceItems() {
        document.querySelectorAll(WORKSPACE_ITEM_SELECTOR).forEach(element => {
            const container = workspaceItemContainer(element);
            if (!container) return;
            const label = workspaceLabel(container) || workspaceLabel(element);
            const surface = label && WORKSPACE_LABEL_SURFACES[label];
            if (!surface) return;
            setHidden(container, !surfaceAllowed(surface), "almdinaPermissionSurfaceHidden");
        });
    }

    function sectionLabel(element) {
        const value = normalizedText(element && element.textContent);
        return Object.prototype.hasOwnProperty.call(WORKSPACE_SECTION_SURFACES, value)
            ? value
            : "";
    }

    function sectionHeaderContainer(element) {
        if (!element) return null;
        return (
            (element.closest && element.closest("[data-block-id], .ce-block, .workspace-block"))
            || element
        );
    }

    function guardWorkspaceSections() {
        document.querySelectorAll(WORKSPACE_HEADER_SELECTOR).forEach(element => {
            const label = sectionLabel(element);
            if (!label) return;
            const allowed = WORKSPACE_SECTION_SURFACES[label].some(surfaceAllowed);
            setHidden(
                sectionHeaderContainer(element),
                !allowed,
                "almdinaPermissionSectionHidden"
            );
        });
    }

    function guardWorkforceActions() {
        if (currentRoute() !== "factory-workforce") return;
        const mayCreate = can("create_users");
        document.querySelectorAll(".page-head .btn-primary, .page-actions .btn-primary").forEach(button => {
            const text = buttonText(button);
            if (/إضافة مستخدم|إنشاء مستخدم|add user|create user/i.test(text)) {
                hideButton(button, !mayCreate);
            }
        });
    }

    function apply() {
        guardWorkspaceItems();
        guardWorkspaceSections();
        guardWorkforceActions();
    }

    function schedule() {
        if (timer) window.clearTimeout(timer);
        timer = window.setTimeout(() => {
            timer = null;
            apply();
        }, 0);
    }

    function startObserver() {
        if (observer || !document.body) return;
        observer = new MutationObserver(mutations => {
            if (mutations.some(mutation => mutation.addedNodes && mutation.addedNodes.length)) {
                schedule();
            }
        });
        observer.observe(document.body, { childList: true, subtree: true });
    }

    function start() {
        startObserver();
        apply();
        if (window.frappe && frappe.router && !frappe.router.__almdinaActionVisibilityGuard) {
            frappe.router.__almdinaActionVisibilityGuard = true;
            frappe.router.on("change", schedule);
        }
        window.addEventListener("almdina:permissions-updated", schedule);
        [100, 300, 800, 1600].forEach(delay => window.setTimeout(apply, delay));
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", start, { once: true });
    } else {
        start();
    }
})();
