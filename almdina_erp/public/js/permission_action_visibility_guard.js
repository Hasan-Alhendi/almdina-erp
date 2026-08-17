(() => {
    "use strict";

    if (window.__almdinaPermissionActionVisibilityGuard) return;
    window.__almdinaPermissionActionVisibilityGuard = true;

    /*
     * This module is a UI compatibility guard only. Server-side permissions
     * remain the authorization source of truth. Keep scans route-scoped and
     * short-lived so Desk mutations outside Almdina surfaces do not trigger
     * repeated document-wide work.
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

    const ALMDINA_WORKSPACE_ROUTES = Object.freeze(new Set([
        "almdina-erp",
        "shop-floor",
        "almdina-control-center",
        "almdina-reports",
        "almdina-settings",
        "almdina-go-live",
    ]));

    const STRUCTURAL_WORKSPACE_ITEM_SELECTOR = [
        ".shortcut-widget-box",
        ".widget.shortcut-widget-box",
        ".link-item",
        ".workspace-link",
        ".sidebar-item-container",
        ".desk-sidebar-item",
        ".standard-sidebar-item",
    ].join(", ");

    const WORKSPACE_ITEM_SELECTOR = `${STRUCTURAL_WORKSPACE_ITEM_SELECTOR}, [data-widget-name]`;

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

    const TRANSIENT_OBSERVER_MS = 5000;
    const pendingRoots = new Set();
    let observer = null;
    let observerStopTimer = null;
    let scheduledFrame = null;

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

    function routeState() {
        if (window.frappe && typeof frappe.get_route === "function") {
            const route = frappe.get_route();
            if (Array.isArray(route) && route.length) {
                const head = String(route[0] || "").toLowerCase();
                if (["workspace", "workspaces"].includes(head)) {
                    return { kind: "workspace", route: routeSlug(route[1] || route[0]) };
                }
                if (["list", "form", "query-report", "report"].includes(head)) {
                    return { kind: "route", route: routeSlug(route[1]) };
                }
                return { kind: "route", route: routeSlug(route[0]) };
            }
        }
        return { kind: "route", route: routeSlug(window.location.pathname || "") };
    }

    function surfaceMode() {
        const state = routeState();
        if (state.route === "factory-workforce") return "workforce";
        if (state.kind === "workspace" || ALMDINA_WORKSPACE_ROUTES.has(state.route)) return "workspace";
        return "none";
    }

    function normalizedText(value) {
        return String(value || "").replace(/\s+/g, " ").trim();
    }

    function buttonText(button) {
        return normalizedText(button && button.textContent);
    }

    function queryWithin(root, selector) {
        if (!root) return [];
        const results = [];
        if (root.nodeType === Node.ELEMENT_NODE && typeof root.matches === "function" && root.matches(selector)) {
            results.push(root);
        }
        if (typeof root.querySelectorAll === "function") results.push(...root.querySelectorAll(selector));
        return results;
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

    function workspaceLabel(element, allowVisibleText = true) {
        if (!element) return "";
        const values = [
            element.getAttribute && element.getAttribute("data-widget-name"),
            element.getAttribute && element.getAttribute("data-name"),
            element.getAttribute && element.getAttribute("data-label"),
            element.getAttribute && element.getAttribute("item-name"),
            element.getAttribute && element.getAttribute("aria-label"),
            element.getAttribute && element.getAttribute("title"),
            element.dataset && element.dataset.widgetName,
            element.dataset && element.dataset.name,
            element.dataset && element.dataset.label,
        ].map(normalizedText).filter(Boolean);

        for (const value of values) {
            if (Object.prototype.hasOwnProperty.call(WORKSPACE_LABEL_SURFACES, value)) return value;
        }

        if (!allowVisibleText) return "";
        const visible = normalizedText(element.textContent);
        if (!visible) return "";
        for (const label of WORKSPACE_LABELS_LONGEST_FIRST) {
            if (visible === label || visible.includes(label)) return label;
        }
        return "";
    }

    function workspaceItemContainer(element) {
        if (!element) return null;
        const structural = element.closest && element.closest(STRUCTURAL_WORKSPACE_ITEM_SELECTOR);
        if (structural) return structural;
        if (typeof element.matches === "function" && element.matches("[data-widget-name]")) return element;
        return null;
    }

    function guardWorkspaceItems(root) {
        queryWithin(root, WORKSPACE_ITEM_SELECTOR).forEach(element => {
            const container = workspaceItemContainer(element);
            if (!container) return;
            const structural = Boolean(
                typeof container.matches === "function"
                && container.matches(STRUCTURAL_WORKSPACE_ITEM_SELECTOR)
            );
            const label = workspaceLabel(container, structural) || workspaceLabel(element, structural);
            const surface = label && WORKSPACE_LABEL_SURFACES[label];
            if (!surface) return;
            setHidden(container, !surfaceAllowed(surface), "almdinaPermissionSurfaceHidden");
        });
    }

    function sectionLabel(element) {
        const value = normalizedText(element && element.textContent);
        return Object.prototype.hasOwnProperty.call(WORKSPACE_SECTION_SURFACES, value) ? value : "";
    }

    function sectionHeaderContainer(element) {
        if (!element) return null;
        return (
            (element.closest && element.closest("[data-block-id], .ce-block, .workspace-block"))
            || element
        );
    }

    function guardWorkspaceSections(root) {
        queryWithin(root, WORKSPACE_HEADER_SELECTOR).forEach(element => {
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

    function guardWorkforceActions(root) {
        queryWithin(root, ".page-head .btn-primary, .page-actions .btn-primary").forEach(button => {
            const text = buttonText(button);
            if (/إضافة مستخدم|إنشاء مستخدم|add user|create user/i.test(text)) {
                hideButton(button, !can("create_users"));
            }
        });
    }

    function applyRoot(root) {
        const mode = surfaceMode();
        if (mode === "workspace") {
            guardWorkspaceItems(root);
            guardWorkspaceSections(root);
            return;
        }
        if (mode === "workforce") guardWorkforceActions(root);
    }

    function compactPendingRoots() {
        const roots = Array.from(pendingRoots);
        return roots.filter((candidate, index) => {
            if (!candidate || candidate.nodeType !== Node.ELEMENT_NODE) return false;
            return !roots.some((other, otherIndex) => (
                otherIndex !== index
                && other
                && other.nodeType === Node.ELEMENT_NODE
                && typeof other.contains === "function"
                && other.contains(candidate)
            ));
        });
    }

    function flushPendingRoots() {
        scheduledFrame = null;
        const roots = compactPendingRoots();
        pendingRoots.clear();
        roots.forEach(applyRoot);
    }

    function scheduleRoot(root) {
        if (!root || root.nodeType !== Node.ELEMENT_NODE) return;
        pendingRoots.add(root);
        if (scheduledFrame !== null) return;
        const schedule = window.requestAnimationFrame || (callback => window.setTimeout(callback, 16));
        scheduledFrame = schedule(flushPendingRoots);
    }

    function disconnectObserver() {
        if (observer) observer.disconnect();
        observer = null;
        if (observerStopTimer) window.clearTimeout(observerStopTimer);
        observerStopTimer = null;
        pendingRoots.clear();
    }

    function startTransientObserver() {
        if (!document.body || surfaceMode() === "none") return;
        observer = new MutationObserver(mutations => {
            for (const mutation of mutations) {
                mutation.addedNodes.forEach(node => {
                    if (node.nodeType === Node.ELEMENT_NODE) scheduleRoot(node);
                    else if (node.parentElement) scheduleRoot(node.parentElement);
                });
            }
        });
        observer.observe(document.body, { childList: true, subtree: true });
        observerStopTimer = window.setTimeout(disconnectObserver, TRANSIENT_OBSERVER_MS);
    }

    function refreshSurface() {
        disconnectObserver();
        const mode = surfaceMode();
        if (mode === "none") return;
        applyRoot(document);
        startTransientObserver();
    }

    function start() {
        refreshSurface();
        if (window.frappe && frappe.router && !frappe.router.__almdinaActionVisibilityGuard) {
            frappe.router.__almdinaActionVisibilityGuard = true;
            frappe.router.on("change", () => window.setTimeout(refreshSurface, 0));
        }
        window.addEventListener("almdina:permissions-updated", refreshSurface);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", start, { once: true });
    } else {
        start();
    }
})();
