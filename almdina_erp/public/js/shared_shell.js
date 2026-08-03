(() => {
    "use strict";

    const APP_NAME = "almdina_erp";
    const CAPABILITY_ROUTE_RULES = Object.freeze([
        { any: ["manage_permissions"], routes: ["factory-permissions", "role"] },
        { any: ["view_users", "manage_users"], routes: ["factory-workforce"] },
        {
            any: [
                "view_factory_settings",
                "edit_factory_cutting_defaults",
                "edit_factory_cost_defaults",
                "edit_factory_production_controls",
                "manage_factory_settings",
            ],
            routes: ["factory-production-settings", "almdina-erp-settings"],
        },
        {
            any: [
                "view_production_routings",
                "create_production_routings",
                "edit_production_routings",
                "delete_production_routings",
                "view_edge_banding_types",
                "create_edge_banding_types",
                "edit_edge_banding_types",
                "delete_edge_banding_types",
            ],
            routes: ["factory-master-data"],
        },
        {
            any: [
                "view_production_routings",
                "create_production_routings",
                "edit_production_routings",
                "delete_production_routings",
            ],
            routes: ["production-routing"],
        },
        {
            any: [
                "view_edge_banding_types",
                "create_edge_banding_types",
                "edit_edge_banding_types",
                "delete_edge_banding_types",
            ],
            routes: ["edge-banding-type"],
        },
        { any: ["approve_order", "reject_order"], routes: ["factory-approval-queue"] },
        { any: ["archive_approved_plan"], routes: ["factory-plan-archive"] },
        { any: ["view_replacements"], routes: ["replacement-piece"] },
        {
            any: ["view_operational_reports", "view_financial_reports"],
            routes: [
                "factory-operations-summary",
                "factory%20operations%20summary",
                "production-incidents-and-replacements",
                "production%20incidents%20and%20replacements",
                "production-stage-performance",
                "production%20stage%20performance",
            ],
        },
    ]);

    let initialized = false;

    function permissions() {
        return window.AlmdinaPermissions || null;
    }

    function navigation() {
        const api = permissions();
        return api && typeof api.navigation === "function" ? api.navigation() : null;
    }

    function can(capability) {
        const api = permissions();
        return Boolean(api && typeof api.can === "function" && api.can(capability));
    }

    function ruleAllowed(rule) {
        const any = Array.isArray(rule.any) ? rule.any : [];
        const all = Array.isArray(rule.all) ? rule.all : [];
        return (any.length === 0 || any.some(can)) && all.every(can);
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
        if (registeredWorkspace(requested) || registeredPage(requested)) {
            return requested;
        }

        for (const workspace of nav && Array.isArray(nav.workspaces) ? nav.workspaces : []) {
            const candidate = routeSlug(workspace);
            if (registeredWorkspace(candidate)) return candidate;
        }
        return "";
    }

    function syncAppDefaultRoute() {
        const nav = navigation();
        if (!nav || !frappe.boot || !nav.default_route) return;

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

    function normalizedRoute(element) {
        const values = [
            element.getAttribute && element.getAttribute("data-link-to"),
            element.getAttribute && element.getAttribute("data-route"),
            element.getAttribute && element.getAttribute("href"),
            element.dataset && element.dataset.linkTo,
            element.dataset && element.dataset.route,
        ];
        return values
            .filter(Boolean)
            .map(value => String(value).toLowerCase().replace(/^#\/?/, "").replace(/^\/?app\//, ""))
            .join(" ");
    }

    function shortcutContainer(element) {
        return (
            element.closest &&
            element.closest(
                ".shortcut-widget-box, .widget.shortcut-widget-box, .link-item, .workspace-link, .card"
            )
        ) || element;
    }

    function hideUnauthorizedShortcuts() {
        const nav = navigation();
        if (!nav || !nav.shared_shell) return;
        document
            .querySelectorAll("[data-link-to], [data-route], a[href*='/app/'], a[href*='/desk/']")
            .forEach(element => {
                const route = normalizedRoute(element);
                const rule = CAPABILITY_ROUTE_RULES.find(item =>
                    item.routes.some(candidate => route.includes(candidate))
                );
                if (!rule) return;
                const allowed = ruleAllowed(rule);
                const container = shortcutContainer(element);
                container.style.setProperty(
                    "display",
                    allowed ? "" : "none",
                    allowed ? "" : "important"
                );
            });
    }

    function routeIsRoot() {
        const route = String((frappe.get_route_str && frappe.get_route_str()) || "").toLowerCase();
        const path = String(window.location.pathname || "").replace(/\/+$/, "").toLowerCase();
        return (
            !route ||
            route === "desktop" ||
            route === "workspaces" ||
            path.endsWith("/app") ||
            path.endsWith("/desk")
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

    function injectStyles() {
        if (document.getElementById("almdina-shared-shell-style")) return;
        const style = document.createElement("style");
        style.id = "almdina-shared-shell-style";
        style.textContent = `
            body.almdina-shared-shell .navbar {border-bottom:1px solid var(--border-color,#e5e7eb)}
            body.almdina-shared-shell .page-head {backdrop-filter:blur(8px)}
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

    function retryConfiguredHome(attempt = 0) {
        if (openConfiguredHome() || attempt >= 20 || !routeIsRoot()) return;
        window.setTimeout(() => retryConfiguredHome(attempt + 1), 100);
    }

    function init() {
        if (initialized) return;
        const nav = navigation();
        if (!nav || !nav.shared_shell) return;

        initialized = true;
        applyShell();
        retryConfiguredHome();

        if (frappe.router && !frappe.router.__almdinaSharedShell) {
            frappe.router.__almdinaSharedShell = true;
            frappe.router.on("change", () => {
                applyShell();
                window.setTimeout(() => retryConfiguredHome(), 0);
                [150, 500].forEach(delay => setTimeout(hideUnauthorizedShortcuts, delay));
            });
        }
        [300, 900, 1800].forEach(delay => setTimeout(applyShell, delay));
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
