(() => {
    "use strict";

    if (window.AlmdinaDeskSidebarUX) return;

    const ROOT_CLASS = "almdina-desk-sidebar";
    let scheduledFrame = null;
    let itemsObserver = null;
    let booted = false;
    let sidebarRenderHooked = false;

    function presentation() {
        return window.AlmdinaShortcutPresentation || null;
    }

    function sharedShellActive() {
        return document.body.classList.contains("almdina-shared-shell");
    }

    function deskReady() {
        return Boolean(
            window.frappe
            && frappe.boot
            && frappe.boot.workspace_sidebar_item
            && presentation()
        );
    }

    function iconIsRendered(iconNode) {
        if (!iconNode) return false;
        const use = iconNode.querySelector("use");
        if (!use) return false;
        return Boolean(use.getAttribute("href") || use.getAttribute("xlink:href"));
    }

    function itemLabel(container) {
        const fromTitle = container.getAttribute("title") || container.getAttribute("data-id") || "";
        const fromDom = container.querySelector(".sidebar-item-label");
        const text = fromDom ? fromDom.textContent : "";
        const api = presentation();
        return api ? api.normalizeText(fromTitle || text) : String(fromTitle || text).trim();
    }

    function resolveIconName(label, linkTo) {
        const api = presentation();
        if (!api) return null;
        return api.iconForLabel(label) || api.iconForLabel(linkTo);
    }

    function patchBootSidebarIcons() {
        const api = presentation();
        const container = frappe.boot && frappe.boot.workspace_sidebar_item;
        if (!api || !container) return;

        Object.values(container).forEach((sidebar) => {
            const items = sidebar && sidebar.items;
            if (!Array.isArray(items)) return;
            items.forEach((item) => {
                if (!item || item.type === "Section Break" || item.type === "Spacer") return;
                const iconName = resolveIconName(item.label, item.link_to);
                if (iconName) item.icon = iconName;
            });
        });
    }

    function applyItemIcon(container) {
        const api = presentation();
        if (!api) return;

        const anchor = container.querySelector(".item-anchor:not(.section-break)");
        if (!anchor) return;

        const label = itemLabel(container);
        const linkTo = anchor.getAttribute("href") || "";
        const iconName = resolveIconName(label, linkTo);
        if (!iconName) return;

        const iconHost = container.querySelector(".sidebar-item-icon[item-icon], .sidebar-item-icon");
        if (!iconHost) return;

        const current = iconHost.getAttribute("item-icon") || iconHost.getAttribute("data-alm-sidebar-icon");
        const isGeneric = !current || current === "list";
        if (!isGeneric && current === iconName && iconIsRendered(iconHost)) return;

        iconHost.setAttribute("item-icon", iconName);
        iconHost.setAttribute("data-alm-sidebar-icon", iconName);
        iconHost.innerHTML = api.renderIcon(iconName, "sm");
    }

    function applySidebarIcons(root) {
        const scope = root && root.querySelectorAll
            ? root
            : document.querySelector(".body-sidebar");
        if (!scope || !scope.querySelectorAll) return;
        scope.querySelectorAll(".sidebar-item-container").forEach((container) => {
            if (container.classList.contains("section-item")) return;
            applyItemIcon(container);
        });
    }

    function ensureItemsObserver() {
        const top = document.querySelector(".body-sidebar-top .sidebar-items");
        if (!top || itemsObserver) return;
        itemsObserver = new MutationObserver(() => schedule());
        itemsObserver.observe(top, { childList: true, subtree: true });
    }

    function hookSidebarRender() {
        if (sidebarRenderHooked) return;
        const app = window.frappe && frappe.app;
        const sidebar = app && app.sidebar;
        if (!sidebar || typeof sidebar.create_sidebar !== "function") return;

        sidebarRenderHooked = true;
        const original = sidebar.create_sidebar.bind(sidebar);
        sidebar.create_sidebar = function patchedCreateSidebar(...args) {
            patchBootSidebarIcons();
            const result = original(...args);
            schedule();
            return result;
        };
    }

    function apply() {
        document.body.classList.toggle(ROOT_CLASS, sharedShellActive());
        patchBootSidebarIcons();
        hookSidebarRender();
        applySidebarIcons(document);
        ensureItemsObserver();
    }

    function schedule() {
        if (scheduledFrame !== null) return;
        const run = window.requestAnimationFrame || ((cb) => window.setTimeout(cb, 16));
        scheduledFrame = run(() => {
            scheduledFrame = null;
            apply();
        });
    }

    function bindLifecycle() {
        if (window.jQuery && !window.__almdinaDeskSidebarExpand) {
            window.__almdinaDeskSidebarExpand = true;
            window.jQuery(document).on("sidebar-expand.almdinaDeskSidebar", schedule);
        }
        if (window.frappe && frappe.router && !frappe.router.__almdinaDeskSidebarUX) {
            frappe.router.__almdinaDeskSidebarUX = true;
            frappe.router.on("change", schedule);
        }
        window.addEventListener("almdina:permissions-updated", schedule);
    }

    function boot() {
        if (!deskReady()) return;
        if (!booted) {
            booted = true;
            bindLifecycle();
        }
        schedule();
    }

    function waitForDesk(attempt) {
        boot();
        hookSidebarRender();
        if (booted || attempt >= 120) return;
        window.setTimeout(() => waitForDesk(attempt + 1), 100);
    }

    if (window.jQuery) {
        window.jQuery(document).on("app_ready.almdinaDeskSidebar", () => waitForDesk(0));
    }
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", () => waitForDesk(0));
    } else {
        waitForDesk(0);
    }

    window.AlmdinaDeskSidebarUX = Object.freeze({ apply, schedule, patchBootSidebarIcons });
})();
