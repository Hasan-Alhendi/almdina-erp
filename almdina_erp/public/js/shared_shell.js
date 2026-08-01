(() => {
    "use strict";

    const APP_NAME = "almdina_erp";

    function permissions() {
        return window.AlmdinaPermissions || null;
    }

    function navigation() {
        const api = permissions();
        return api && typeof api.navigation === "function" ? api.navigation() : null;
    }

    function workspaceName(page) {
        if (typeof page === "string") return page;
        if (!page || typeof page !== "object") return "";
        return String(page.name || page.title || page.label || "");
    }

    function trimBootMetadata() {
        const nav = navigation();
        if (!nav || !frappe.boot) return;
        const allowed = new Set(nav.workspaces || []);

        if (frappe.boot.workspaces && Array.isArray(frappe.boot.workspaces.pages) && allowed.size) {
            frappe.boot.workspaces.pages = frappe.boot.workspaces.pages.filter(page =>
                allowed.has(workspaceName(page))
            );
            frappe.boot.allowed_workspaces = frappe.boot.workspaces.pages;
        }

        if (nav.app_only && frappe.boot.apps_data && Array.isArray(frappe.boot.apps_data.apps)) {
            frappe.boot.apps_data.apps = frappe.boot.apps_data.apps.filter(app => {
                const name = app && typeof app === "object" ? app.name : app;
                return name === APP_NAME;
            });
            frappe.boot.apps_data.default_path = nav.default_route;
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
        if (!nav || !routeIsRoot()) return;
        const home = String(nav.home_page || "almdina-erp");
        if (frappe.set_route) {
            frappe.set_route(home);
            return;
        }
        window.location.href = String(nav.default_route || `/app/${home}`);
    }

    function injectStyles() {
        if (document.getElementById("almdina-shared-shell-style")) return;
        const style = document.createElement("style");
        style.id = "almdina-shared-shell-style";
        style.textContent = `
            body.almdina-shared-shell .navbar {
                border-bottom: 1px solid var(--border-color, #e5e7eb);
            }
            body.almdina-shared-shell .page-head {
                backdrop-filter: blur(8px);
            }
            .almdina-sf-tabs {
                position: sticky;
                top: 0;
                z-index: 20;
                display: flex;
                flex-wrap: wrap;
                align-items: center;
                gap: 8px;
                padding: 10px;
                background: var(--fg-color, #fff);
                border: 1px solid var(--border-color, #e5e7eb);
                border-radius: 14px;
                margin-bottom: 12px;
            }
            .almdina-sf-tab {
                appearance: none;
                border: 1px solid var(--border-color, #dfe3e8);
                background: var(--control-bg, #fff);
                color: var(--text-color, #1f272e);
                min-height: 42px;
                padding: 8px 16px;
                border-radius: 10px;
                font-size: 14px;
                font-weight: 700;
                cursor: pointer;
            }
            .almdina-sf-tab.is-active {
                background: var(--primary, #2490ef);
                border-color: var(--primary, #2490ef);
                color: #fff;
            }
            .almdina-sf-refresh {
                margin-inline-start: auto;
                min-height: 42px !important;
                font-weight: 700;
            }
            .almdina-sf-shell { padding: 2px 0 24px; }
            .almdina-sf-list-title { font-size: 1.05rem; font-weight: 800; margin: 0 0 10px; }
            .almdina-sf-list { display: grid; gap: 10px; }
            .almdina-sf-order-card {
                padding: 14px !important;
                border-radius: 14px !important;
                border: 1px solid var(--border-color, #e5e7eb) !important;
                box-shadow: 0 1px 3px rgba(0,0,0,.05);
                cursor: pointer;
            }
            .almdina-sf-order-card:hover { box-shadow: 0 4px 14px rgba(0,0,0,.08); }
            .almdina-sf-order-card .sf-open-btn,
            .almdina-sf-actions .btn {
                min-height: 42px;
                padding: 9px 14px;
                font-size: 14px;
                font-weight: 700;
                border-radius: 10px;
            }
            .almdina-sf-actions {
                display: flex;
                flex-wrap: wrap;
                gap: 8px;
                margin-bottom: 12px;
            }
            .almdina-sf-detail-title { font-size: 1.15rem; margin: 0 0 4px; }
            .almdina-sf-pieces-wrap,
            .almdina-sf-plan-wrap {
                overflow: auto;
                -webkit-overflow-scrolling: touch;
                border: 1px solid var(--border-color, #e5e7eb);
                border-radius: 12px;
                background: var(--fg-color, #fff);
                padding: 8px;
            }
            .almdina-sf-account-card {
                border: 1px solid var(--border-color, #e5e7eb);
                border-radius: 14px;
                padding: 16px;
                background: var(--fg-color, #fff);
                max-width: 560px;
            }
            .almdina-sf-account-row {
                display: flex;
                justify-content: space-between;
                gap: 12px;
                padding: 10px 0;
                border-bottom: 1px solid var(--border-color, #edf0f2);
                font-size: 14px;
            }
            .almdina-sf-account-row:last-of-type { border-bottom: 0; }
            .almdina-sf-empty {
                padding: 28px 18px;
                text-align: center;
                border: 1px dashed var(--border-color, #d7dde3);
                border-radius: 14px;
                color: var(--text-muted, #6b7280);
                background: var(--subtle-fg, #fafafa);
            }
            @media (max-width: 600px) {
                .almdina-sf-tabs { border-radius: 10px; }
                .almdina-sf-tab { flex: 1 1 calc(33% - 8px); padding: 8px 6px; }
                .almdina-sf-refresh { flex: 1 1 100%; margin-inline-start: 0; }
                .almdina-sf-actions .btn { flex: 1 1 calc(50% - 8px); }
            }
        `;
        document.head.appendChild(style);
    }

    function applyShell() {
        const nav = navigation();
        if (!nav || !nav.shared_shell) return;
        document.body.classList.add("almdina-shared-shell");
        document.body.dataset.almdinaProfile = String(nav.profile || "shared");
        trimBootMetadata();
        hideOtherAppCards();
        injectStyles();
    }

    function init() {
        applyShell();
        openConfiguredHome();
        if (frappe.router && !frappe.router.__almdinaSharedShell) {
            frappe.router.__almdinaSharedShell = true;
            frappe.router.on("change", applyShell);
        }
        [300, 900, 1800].forEach(delay => setTimeout(applyShell, delay));
    }

    function waitForBoot(attempt) {
        if (window.frappe && frappe.boot && permissions()) {
            init();
            return;
        }
        if (attempt >= 60) return;
        setTimeout(() => waitForBoot(attempt + 1), 150);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", () => waitForBoot(0));
    } else {
        waitForBoot(0);
    }
})();
