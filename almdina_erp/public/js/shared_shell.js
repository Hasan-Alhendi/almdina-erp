(() => {
    "use strict";

    const APP_NAME = "almdina_erp";
    const PERMISSION_CONTEXT_VERSION = 6;
    const FACTORY_SETTINGS_CONSOLE_ROUTE = "factory-production-settings";
    const LEGACY_FACTORY_SETTINGS_ROUTE = "almdina-erp-settings";
    const SURFACE_ROUTE_RULES = Object.freeze([
        { surface: "orders", routes: ["door-cutting-order"] },
        { surface: "customer_admin", routes: ["customer"] },
        { surface: "cutting_plans", routes: ["cutting-plan"] },
        { surface: "production_stages", routes: ["production-stage"] },
        { surface: "production_incidents", routes: ["production-incident"] },
        { surface: "replacements", routes: ["replacement-piece"] },
        { surface: "approval_queue", routes: ["factory-approval-queue"] },
        { surface: "plan_archive", routes: ["factory-plan-archive"] },
        { surface: "factory_master_data", routes: ["factory-master-data"] },
        { surface: "production_routings", routes: ["production-routing"] },
        { surface: "edge_banding_types", routes: ["edge-banding-type"] },
        {
            surface: "factory_settings",
            routes: [FACTORY_SETTINGS_CONSOLE_ROUTE, LEGACY_FACTORY_SETTINGS_ROUTE],
        },
        { surface: "workforce", routes: ["factory-workforce"] },
        { surface: "permissions", routes: ["factory-permissions"] },
        {
            surface: "role_admin",
            routes: [
                "role",
                "role-permission-manager",
                "permission-inspector",
                "permission-type",
                "user-permission",
                "user",
            ],
        },
        {
            surface: "report_factory_operations_summary",
            routes: ["factory-operations-summary"],
        },
        {
            surface: "report_factory_order_analysis",
            routes: ["factory-order-analysis"],
        },
        {
            surface: "report_production_stage_performance",
            routes: ["production-stage-performance"],
        },
        {
            surface: "report_production_incidents_and_replacements",
            routes: ["production-incidents-and-replacements"],
        },
        { surface: "report_board_usage_analysis", routes: ["board-usage-analysis"] },
        {
            surface: "report_piece_size_usage_analysis",
            routes: ["piece-size-usage-analysis"],
        },
        {
            surface: "report_order_stock_availability",
            routes: ["order-stock-availability"],
        },
        { surface: "report_remnant_inventory", routes: ["remnant-inventory"] },
    ]);
    const ALMDINA_WORKSPACE_ROUTES = Object.freeze(
        new Set([
            "almdina-erp",
            "shop-floor",
            "almdina-control-center",
            "almdina-reports",
            "almdina-settings",
            "almdina-go-live",
        ])
    );

    let initialized = false;
    let observer = null;
    let observerTimer = null;
    let redirecting = false;
    let lastDeniedRoute = "";

    function permissions() {
        return window.AlmdinaPermissions || null;
    }

    function navigation() {
        const api = permissions();
        return api && typeof api.navigation === "function" ? api.navigation() : null;
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
        const text = String(value || "").trim();
        if (!text) return "";
        if (frappe.router && typeof frappe.router.slug === "function") {
            return frappe.router.slug(text);
        }
        return text
            .toLowerCase()
            .replace(/[^a-z0-9\u0600-\u06ff]+/g, "-")
            .replace(/^-+|-+$/g, "");
    }

    function canonicalRoute(value) {
        let text = String(value || "").trim();
        if (!text) return "";
        try {
            if (/^https?:\/\//i.test(text)) {
                text = new URL(text, window.location.origin).pathname;
            }
        } catch (error) {
            console.debug("تعذر تحليل رابط أثناء تطبيق الصلاحيات", error);
        }
        try {
            text = decodeURIComponent(text);
        } catch (error) {
            console.debug("تعذر فك ترميز رابط أثناء تطبيق الصلاحيات", error);
        }
        text = text
            .replace(/^#\/?/, "")
            .replace(/^\/+/, "")
            .replace(/^(app|desk)\//i, "")
            .split("?")[0]
            .split("#")[0];

        const typed = text.match(/^(list|form)\/([^/]+)/i);
        if (typed) return routeSlug(typed[2]);
        const report = text.match(/^(query-report|report)\/(.+)$/i);
        if (report) return routeSlug(report[2]);
        const firstSegment = text.split("/")[0];
        return routeSlug(firstSegment || text);
    }

    function registeredWorkspace(route) {
        const key = routeSlug(route);
        return Boolean(
            key
            && frappe.workspaces
            && Object.prototype.hasOwnProperty.call(frappe.workspaces, key)
        );
    }

    function registeredPage(route) {
        const key = String(route || "").trim();
        return Boolean(
            key
            && frappe.boot
            && frappe.boot.page_info
            && Object.prototype.hasOwnProperty.call(frappe.boot.page_info, key)
        );
    }

    function resolveHomeRoute(nav) {
        const requested = routeSlug(nav && nav.home_page);
        if (requested === "door-cutting-order" && surfaceAllowed("orders")) {
            return requested;
        }
        if (registeredWorkspace(requested) || registeredPage(requested)) {
            return requested;
        }
        for (const workspace of nav && Array.isArray(nav.workspaces) ? nav.workspaces : []) {
            const candidate = routeSlug(workspace);
            if (registeredWorkspace(candidate)) return candidate;
        }
        return "";
    }

    function allowedWorkspaceRoutes(nav) {
        return new Set(
            nav && Array.isArray(nav.workspaces)
                ? nav.workspaces.map(routeSlug).filter(Boolean)
                : []
        );
    }

    function workspaceAllowed(route) {
        const nav = navigation();
        if (!nav || !nav.shared_shell) return true;
        const key = canonicalRoute(route);
        if (!ALMDINA_WORKSPACE_ROUTES.has(key)) return true;
        return allowedWorkspaceRoutes(nav).has(key);
    }

    function ruleForRoutes(routes) {
        const requested = new Set(routes.filter(Boolean));
        return SURFACE_ROUTE_RULES.find(rule =>
            rule.routes.some(route => requested.has(route))
        ) || null;
    }

    function normalizedRoutes(element) {
        const values = [
            element.getAttribute && element.getAttribute("data-link-to"),
            element.getAttribute && element.getAttribute("data-route"),
            element.getAttribute && element.getAttribute("data-name"),
            element.getAttribute && element.getAttribute("href"),
            element.dataset && element.dataset.linkTo,
            element.dataset && element.dataset.route,
        ];
        return [...new Set(values.filter(Boolean).map(canonicalRoute).filter(Boolean))];
    }

    function currentRouteCandidates() {
        const values = [];
        if (frappe.get_route_str && typeof frappe.get_route_str === "function") {
            values.push(frappe.get_route_str());
        }
        if (frappe.get_route && typeof frappe.get_route === "function") {
            const route = frappe.get_route();
            if (Array.isArray(route)) values.push(...route);
            else if (route) values.push(route);
        }
        values.push(window.location.pathname || "");
        return [...new Set(values.map(canonicalRoute).filter(Boolean))];
    }

    function redirectLegacyFactorySettingsRoute() {
        if (redirecting) return false;
        const routes = currentRouteCandidates();
        if (!routes.includes(LEGACY_FACTORY_SETTINGS_ROUTE)) return false;
        if (routes.includes(FACTORY_SETTINGS_CONSOLE_ROUTE)) return false;

        redirecting = true;
        const navigationPromise = typeof frappe.set_route === "function"
            ? Promise.resolve(frappe.set_route(FACTORY_SETTINGS_CONSOLE_ROUTE))
            : Promise.resolve(window.location.replace(`/desk/${FACTORY_SETTINGS_CONSOLE_ROUTE}`));
        navigationPromise.finally(() => {
            window.setTimeout(() => {
                redirecting = false;
            }, 100);
        });
        return true;
    }

    function installFactorySettingsCanonicalRedirect() {
        if (!frappe.router || frappe.router.__almdinaFactorySettingsCanonicalRedirect) return;
        frappe.router.__almdinaFactorySettingsCanonicalRedirect = true;
        frappe.router.on("change", () => {
            window.setTimeout(redirectLegacyFactorySettingsRoute, 0);
        });
    }

    function shortcutContainer(element) {
        return (
            element.closest &&
            element.closest(
                ".shortcut-widget-box, .widget.shortcut-widget-box, .link-item, .workspace-link, .sidebar-item-container, .desk-sidebar-item, .card"
            )
        ) || element;
    }

    function setPermissionVisibility(element, allowed) {
        if (!element || !element.style) return;
        if (!allowed) {
            element.dataset.almdinaPermissionHidden = "1";
            element.style.setProperty("display", "none", "important");
            return;
        }
        if (element.dataset.almdinaPermissionHidden === "1") {
            delete element.dataset.almdinaPermissionHidden;
            element.style.removeProperty("display");
        }
    }

    function syncAppDefaultRoute() {
        const nav = navigation();
        if (!nav || !nav.app_only || !frappe.boot || !nav.default_route) return;

        if (frappe.boot.apps_data && typeof frappe.boot.apps_data === "object") {
            frappe.boot.apps_data.default_path = nav.default_route;
        }
        if (Array.isArray(frappe.boot.app_data)) {
            const app = frappe.boot.app_data.find(item =>
                item && (item.app_name || item.name) === APP_NAME
            );
            if (app) app.app_route = nav.default_route;
        }
    }

    function hideOtherAppCards() {
        const nav = navigation();
        if (!nav || !nav.app_only) return;
        document
            .querySelectorAll(".dropdown-menu-item[data-app-route], .app-card[data-app-name]")
            .forEach(element => {
                const name = element.getAttribute("data-name") || element.getAttribute("data-app-name") || "";
                const route = element.getAttribute("data-app-route") || "";
                const isAlmdina = name === APP_NAME || route.includes("almdina");
                if (name && !isAlmdina) {
                    element.style.setProperty("display", "none", "important");
                }
            });
    }

    function hideUnauthorizedShortcuts() {
        const nav = navigation();
        if (!nav || !nav.shared_shell) return;
        document
            .querySelectorAll("[data-link-to], [data-route], [data-name], a[href*='/app/'], a[href*='/desk/']")
            .forEach(element => {
                const routes = normalizedRoutes(element);
                if (!routes.length) return;
                const container = shortcutContainer(element);
                const workspaceRoute = routes.find(route => ALMDINA_WORKSPACE_ROUTES.has(route));
                if (workspaceRoute) {
                    setPermissionVisibility(container, workspaceAllowed(workspaceRoute));
                    return;
                }
                const rule = ruleForRoutes(routes);
                if (!rule) return;
                setPermissionVisibility(container, surfaceAllowed(rule.surface));
            });
    }

    function routeIsRoot() {
        const route = String((frappe.get_route_str && frappe.get_route_str()) || "").toLowerCase();
        const path = String(window.location.pathname || "").replace(/\/+$/, "").toLowerCase();
        return (
            !route
            || route === "desktop"
            || route === "workspaces"
            || path.endsWith("/app")
            || path.endsWith("/desk")
        );
    }

    function openConfiguredHome() {
        const nav = navigation();
        if (!nav || !nav.shared_shell || !nav.home_page || !routeIsRoot()) return true;
        const home = resolveHomeRoute(nav);
        if (!home) return false;
        if (typeof frappe.set_route === "function") {
            frappe.set_route(home);
            return true;
        }
        window.location.replace(`/desk/${home}`);
        return true;
    }

    function protectedRouteDecision() {
        const nav = navigation();
        if (!nav || !nav.shared_shell) return null;
        const routes = currentRouteCandidates();
        const workspaceRoute = routes.find(route => ALMDINA_WORKSPACE_ROUTES.has(route));
        if (workspaceRoute && !workspaceAllowed(workspaceRoute)) {
            return { allowed: false, route: workspaceRoute };
        }
        const rule = ruleForRoutes(routes);
        if (!rule) return null;
        return {
            allowed: surfaceAllowed(rule.surface),
            route: rule.routes[0],
            surface: rule.surface,
        };
    }

    function guardCurrentRoute() {
        if (redirecting || routeIsRoot()) return true;
        const decision = protectedRouteDecision();
        if (!decision || decision.allowed) return true;

        const nav = navigation();
        const home = resolveHomeRoute(nav);
        if (!home || canonicalRoute(home) === canonicalRoute(decision.route)) return false;

        const deniedRoute = currentRouteCandidates().join("|");
        if (lastDeniedRoute !== deniedRoute) {
            lastDeniedRoute = deniedRoute;
            frappe.show_alert(
                {
                    message: __("لا تملك صلاحية الوصول إلى هذا القسم."),
                    indicator: "orange",
                },
                5
            );
        }
        redirecting = true;
        Promise.resolve(frappe.set_route(home)).finally(() => {
            window.setTimeout(() => {
                redirecting = false;
            }, 100);
        });
        return false;
    }

    function injectStyles() {
        if (document.getElementById("almdina-shared-shell-style")) return;
        const style = document.createElement("style");
        style.id = "almdina-shared-shell-style";
        style.textContent = `
            body.almdina-shared-shell .navbar {border-bottom:1px solid var(--border-color,#e5e7eb)}
            body.almdina-shared-shell .page-head {backdrop-filter:blur(8px)}
            [data-almdina-permission-hidden="1"]{display:none!important}
            .almdina-sf-tabs{position:sticky;top:0;z-index:20;display:flex;flex-wrap:wrap;align-items:center;gap:8px;padding:10px;background:var(--fg-color,#fff);border:1px solid var(--border-color,#e5e7eb);border-radius:14px;margin-bottom:12px}
            .almdina-sf-tab{appearance:none;border:1px solid var(--border-color,#dfe3e8);background:var(--control-bg,#fff);color:var(--text-color,#1f272e);min-height:42px;padding:8px 16px;border-radius:10px;font-size:14px;font-weight:700;cursor:pointer}
            .almdina-sf-tab.is-active{background:var(--primary,#2490ef);border-color:var(--primary,#2490ef);color:#fff}
            .almdina-sf-refresh{margin-inline-start:auto;min-height:42px!important;font-weight:700}
            .almdina-sf-shell{padding:2px 0 24px}.almdina-sf-list-title{font-size:1.05rem;font-weight:800;margin:0 0 10px}.almdina-sf-list{display:grid;gap:10px}
            .almdina-sf-order-card{padding:14px!important;border-radius:14px!important;border:1px solid var(--border-color,#e5e7eb)!important;box-shadow:0 1px 3px rgba(0,0,0,.05);cursor:pointer}.almdina-sf-order-card:hover{box-shadow:0 4px 14px rgba(0,0,0,.08)}
            .almdina-sf-order-card .sf-open-btn,.almdina-sf-actions .btn{min-height:42px;padding:9px 14px;font-size:14px;font-weight:700;border-radius:10px}.almdina-sf-actions{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:12px}.almdina-sf-detail-title{font-size:1.15rem;margin:0 0 4px}
            .almdina-sf-pieces-wrap,.almdina-sf-plan-wrap{overflow:auto;-webkit-overflow-scrolling:touch;border:1px solid var(--border-color,#e5e7eb);border-radius:12px;background:var(--fg-color,#fff);padding:8px}
            .almdina-sf-account-card{border:1px solid var(--border-color,#e5e7eb);border-radius:14px;padding:16px;background:var(--fg-color,#fff);max-width:560px}.almdina-sf-account-row{display:flex;justify-content:space-between;gap:12px;padding:10px 0;border-bottom:1px solid var(--border-color,#edf0f2);font-size:14px}.almdina-sf-account-row:last-of-type{border-bottom:0}
            .almdina-sf-empty{padding:28px 18px;text-align:center;border:1px dashed var(--border-color,#d7dde3);border-radius:14px;color:var(--text-muted,#6b7280);background:var(--subtle-fg,#fafafa)}
            @media(max-width:600px){.almdina-sf-tabs{border-radius:10px}.almdina-sf-tab{flex:1 1 calc(33% - 8px);padding:8px 6px}.almdina-sf-refresh{flex:1 1 100%;margin-inline-start:0}.almdina-sf-actions .btn{flex:1 1 calc(50% - 8px)}}
        `;
        document.head.appendChild(style);
    }

    function applyShell() {
        const nav = navigation();
        if (!nav || !nav.shared_shell) return;
        document.body.classList.add("almdina-shared-shell");
        document.body.dataset.almdinaProfile = String(nav.profile || "shared");
        syncAppDefaultRoute();
        hideOtherAppCards();
        hideUnauthorizedShortcuts();
        injectStyles();
    }

    function schedulePermissionScan() {
        if (observerTimer) window.clearTimeout(observerTimer);
        observerTimer = window.setTimeout(() => {
            observerTimer = null;
            hideUnauthorizedShortcuts();
        }, 40);
    }

    function observeDeskMutations() {
        if (observer || !document.body) return;
        observer = new MutationObserver(mutations => {
            if (mutations.some(mutation => mutation.addedNodes && mutation.addedNodes.length)) {
                schedulePermissionScan();
            }
        });
        observer.observe(document.body, { childList: true, subtree: true });
    }

    function retryConfiguredHome(attempt = 0) {
        if (openConfiguredHome() || attempt >= 20 || !routeIsRoot()) return;
        window.setTimeout(() => retryConfiguredHome(attempt + 1), 100);
    }

    function startShell() {
        applyShell();
        observeDeskMutations();
        if (!redirectLegacyFactorySettingsRoute()) {
            retryConfiguredHome();
            window.setTimeout(guardCurrentRoute, 0);
        }

        if (frappe.router && !frappe.router.__almdinaSharedShell) {
            frappe.router.__almdinaSharedShell = true;
            frappe.router.on("change", () => {
                applyShell();
                window.setTimeout(() => {
                    if (redirectLegacyFactorySettingsRoute()) return;
                    retryConfiguredHome();
                    guardCurrentRoute();
                }, 0);
                [100, 300, 800].forEach(delay => setTimeout(hideUnauthorizedShortcuts, delay));
            });
        }
        if (!window.__almdinaPermissionUpdateListener) {
            window.__almdinaPermissionUpdateListener = true;
            window.addEventListener("almdina:permissions-updated", () => {
                applyShell();
                if (!redirectLegacyFactorySettingsRoute()) guardCurrentRoute();
            });
        }
        [100, 300, 900, 1800].forEach(delay => setTimeout(applyShell, delay));
    }

    function init() {
        if (initialized) return;
        const nav = navigation();
        if (!nav || !nav.shared_shell) return;
        initialized = true;

        const api = permissions();
        if (
            api
            && typeof api.version === "function"
            && api.version() < PERMISSION_CONTEXT_VERSION
            && typeof api.refresh === "function"
        ) {
            api.refresh().then(startShell).catch(startShell);
            return;
        }
        startShell();
    }

    function deskIsReady() {
        return Boolean(
            window.frappe
            && frappe.boot
            && frappe.app
            && frappe.router
            && frappe.router.current_route !== null
            && frappe.workspaces
            && permissions()
        );
    }

    function waitForDesk(attempt) {
        if (deskIsReady()) {
            installFactorySettingsCanonicalRedirect();
            redirectLegacyFactorySettingsRoute();
            init();
            return;
        }
        if (attempt >= 100) return;
        setTimeout(() => waitForDesk(attempt + 1), 100);
    }

    if (window.jQuery) {
        window.jQuery(document).on("app_ready.almdinaSharedShell", () => waitForDesk(0));
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", () => waitForDesk(0));
    } else {
        waitForDesk(0);
    }
})();
