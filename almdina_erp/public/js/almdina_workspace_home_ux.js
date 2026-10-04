(() => {
    "use strict";

    if (window.AlmdinaWorkspaceHomeUX) return;

    const WORKSPACE_SLUG = "almdina-erp";
    const WORKSPACE_NAME = "Almdina ERP";
    const WORKSPACE_PAGE_TITLE = "إدارة المعمل";
    const ROOT_CLASS = "almdina-workspace-home";
    const POLISH_FLAG = "data-almdina-workspace-home-polish";
    const SHORTCUT_CLASS = "alm-shortcut";

    /**
     * Stable Editor.js block ids from workspace/almdina_erp.json — not visible labels.
     */
    const SECTION_BY_BLOCK_ID = Object.freeze({
        "master-data-header": { id: "master", meta: "3 وحدات رئيسية" },
        "system-management-header": { id: "system", meta: "4 وحدات" },
        "factory-operations-header": { id: "ops", meta: "سير عمل الصالة والمعمل" },
        "reports-header": { id: "reports", meta: "البيانات الإحصائية والتحليلية" },
    });

    /** Workspace content block id → Frappe link_to / route. */
    const SHORTCUT_BLOCK_TO_LINK = Object.freeze({
        "customers-shortcut": "Customer",
        "edge-types-shortcut": "Edge Banding Type",
        "settings-shortcut": "factory-production-settings",
        "role-management-shortcut": "Role",
        "permission-management-shortcut": "factory-permissions",
        "user-management-shortcut": "factory-workforce",
        "routing-management-shortcut": "factory-master-data",
        "orders-shortcut": "Door Cutting Order",
        "stages-shortcut": "shop-floor-inbox",
    });

    // Backward-compatible export name used by contract tests.
    const SECTION_PRESENTATION = SECTION_BY_BLOCK_ID;

    const presentationApi = () => window.AlmdinaShortcutPresentation || null;
    const frontendApi = () => window.AlmdinaFrontend || null;

    const observers = new Set();
    let lifecycle = null;
    let scheduledFrame = null;
    let booted = false;
    let active = false;
    let rootObserver = null;
    let breadcrumbObserver = null;
    let pageWaitObserver = null;

    function trackObserver(observer) {
        if (!observer || typeof observer.disconnect !== "function") return observer;
        observers.add(observer);
        return observer;
    }

    function disposeObservers() {
        observers.forEach((observer) => {
            try {
                observer.disconnect();
            } catch (_error) {
                /* ignore */
            }
        });
        observers.clear();
        rootObserver = null;
        breadcrumbObserver = null;
        pageWaitObserver = null;
    }

    function dispose() {
        if (scheduledFrame !== null) {
            const cancel = window.cancelAnimationFrame || window.clearTimeout;
            cancel(scheduledFrame);
            scheduledFrame = null;
        }
        disposeObservers();
        if (lifecycle && typeof lifecycle.dispose === "function") {
            lifecycle.dispose();
        }
        lifecycle = null;
        active = false;
        document.body.classList.remove(ROOT_CLASS);
    }

    function normalizeText(value) {
        const api = presentationApi();
        if (api) return api.normalizeText(value);
        return String(value || "").replace(/\s+/g, " ").trim();
    }

    function slugify(value) {
        const text = String(value || "").trim();
        if (!text) return "";
        if (window.frappe && frappe.router && typeof frappe.router.slug === "function") {
            return frappe.router.slug(text);
        }
        return text.toLowerCase().replace(/ /g, "-");
    }

    function workspaceRouteSegment() {
        if (!window.frappe || typeof frappe.get_route !== "function") return "";
        const route = frappe.get_route() || [];
        if (route[0] !== "Workspaces") return "";
        return String(route[1] === "private" ? route[2] : route[1] || "").trim();
    }

    function isTargetWorkspace() {
        const segment = workspaceRouteSegment();
        if (!segment) return false;
        if (slugify(segment) === WORKSPACE_SLUG) return true;
        if (segment === WORKSPACE_NAME) return true;
        if (segment === __("Almdina ERP")) return true;
        return false;
    }

    function workspacePage() {
        return document.getElementById("page-Workspaces");
    }

    function editorRoot() {
        const page = workspacePage();
        if (page) {
            const scoped = page.querySelector(".editor-js-container");
            if (scoped) return scoped;
        }
        return document.querySelector(".layout-main-section .editor-js-container");
    }

    function blockIdFromNode(node) {
        if (!node || !node.closest) return "";
        const block = node.closest(".ce-block");
        return normalizeText((block && (block.dataset.id || block.getAttribute("data-id"))) || "");
    }

    function sectionFromBlockId(blockId) {
        return SECTION_BY_BLOCK_ID[blockId] || null;
    }

    function shortcutLinkTo(widget) {
        if (!widget) return "";
        const stamped = normalizeText(widget.getAttribute("data-alm-link-to") || "");
        if (stamped) return stamped;

        const blockId = blockIdFromNode(widget);
        if (blockId && SHORTCUT_BLOCK_TO_LINK[blockId]) {
            return SHORTCUT_BLOCK_TO_LINK[blockId];
        }

        const api = presentationApi();
        if (!api) return "";

        // Frappe stamps data-widget-name with the shortcut name (label), not link_to.
        // Resolve through the stable label→link_to bridge only as a fallback.
        const widgetName = normalizeText(widget.getAttribute("data-widget-name") || "");
        if (widgetName && typeof api.linkToForLabel === "function") {
            return api.linkToForLabel(widgetName) || "";
        }
        return "";
    }

    function shortcutMeta(linkTo) {
        const api = presentationApi();
        if (!api) return null;
        if (typeof api.metaForLinkTo === "function") {
            return api.metaForLinkTo(linkTo);
        }
        return null;
    }

    function renderIcon(name) {
        const api = presentationApi();
        if (api) return api.renderIcon(name, "md");
        if (window.frappe && frappe.utils && typeof frappe.utils.icon === "function") {
            return frappe.utils.icon(name, "md");
        }
        return "";
    }

    function iconIsRendered(iconNode) {
        if (!iconNode) return false;
        const use = iconNode.querySelector("use");
        if (!use) return false;
        return Boolean(use.getAttribute("href") || use.getAttribute("xlink:href"));
    }

    function resolveShortcutIcon(section, meta) {
        const api = presentationApi();
        if (section === "reports") {
            return (api && api.REPORTS_SECTION_ICON) || meta.icon || "es-line-reports";
        }
        return meta.icon;
    }

    function ensureShortcutIcon(head, iconName) {
        if (!head) return null;
        let iconNode = head.querySelector(".alm-workspace-shortcut-icon");
        if (!iconNode) {
            iconNode = document.createElement("span");
            iconNode.className = "alm-workspace-shortcut-icon";
            iconNode.setAttribute("aria-hidden", "true");
            head.insertBefore(iconNode, head.firstChild);
        }
        if (iconNode.getAttribute("data-alm-icon") === iconName && iconIsRendered(iconNode)) {
            return iconNode;
        }
        const badge = iconNode.querySelector(".alm-workspace-shortcut-badge");
        iconNode.setAttribute("data-alm-icon", iconName);
        iconNode.innerHTML = renderIcon(iconName);
        if (badge) iconNode.appendChild(badge);
        return iconNode;
    }

    function enhanceHeaders(root) {
        root.querySelectorAll(".ce-block").forEach((block) => {
            const header = block.querySelector(".widget.header");
            if (!header) return;
            const presentation = sectionFromBlockId(block.dataset.id || block.getAttribute("data-id") || "");
            if (!presentation) return;

            header.setAttribute("data-alm-section", presentation.id);
            const titleHost = header.querySelector(".ce-header") || header.querySelector(".h4") || header;
            titleHost.classList.add("alm-workspace-section-head");
            if (header.querySelector(".alm-workspace-section-meta")) return;
            const meta = document.createElement("span");
            meta.className = "alm-workspace-section-meta";
            meta.textContent = __(presentation.meta);
            titleHost.appendChild(meta);
        });
    }

    function assignShortcutSections(root) {
        let currentSection = "";
        root.querySelectorAll(".ce-block").forEach((block) => {
            const header = block.querySelector(".widget.header");
            if (header) {
                const presentation = sectionFromBlockId(block.dataset.id || block.getAttribute("data-id") || "");
                if (presentation) currentSection = presentation.id;
                return;
            }
            const widget = block.querySelector(".shortcut-widget-box");
            if (widget && currentSection) {
                widget.setAttribute("data-alm-section", currentSection);
            }
        });
    }

    function normalizeWorkspaceTrail(crumbs) {
        if (!crumbs) return;

        const items = crumbs.querySelectorAll("li");
        const currentLink = crumbs.querySelector("li:last-child a.title-text");
        if (
            items.length === 2
            && currentLink
            && normalizeText(currentLink.textContent) === normalizeText(__(WORKSPACE_PAGE_TITLE))
            && crumbs.querySelector("li:first-child a")
        ) {
            return;
        }

        const home = crumbs.querySelector("li:first-child a");
        if (home) {
            home.href = "/desk";
            if (!home.querySelector("svg") && window.frappe && frappe.utils && typeof frappe.utils.icon === "function") {
                home.innerHTML = frappe.utils.icon("home", "sm");
            }
        }

        [...crumbs.querySelectorAll("li")].slice(1).forEach((item) => item.remove());

        let current = crumbs.querySelector("li:last-child");
        if (current === crumbs.querySelector("li:first-child")) {
            current = document.createElement("li");
            crumbs.appendChild(current);
        }

        current.classList.add("disabled", "ellipsis");
        current.querySelectorAll(".dropdown, .menu-btn-group, button").forEach((node) => node.remove());

        let link = current.querySelector("a");
        if (!link) {
            link = document.createElement("a");
            current.appendChild(link);
        }
        link.className = "title-text";
        link.textContent = __(WORKSPACE_PAGE_TITLE);
        link.removeAttribute("href");
    }

    /**
     * Minimal DOM ownership: move Frappe's indicator/arrow into presentation hosts once.
     * Re-runs are driven by the single root MutationObserver (no per-widget observers).
     */
    function layoutShortcutControls(root) {
        root.querySelectorAll(".shortcut-widget-box").forEach((widget) => {
            const head = widget.querySelector(".widget-head");
            if (!head) return;

            let arrowHost = head.querySelector(".alm-workspace-shortcut-arrow");
            if (!arrowHost) {
                arrowHost = document.createElement("span");
                arrowHost.className = "alm-workspace-shortcut-arrow";
                arrowHost.setAttribute("aria-hidden", "true");
                head.appendChild(arrowHost);
            }

            const control = head.querySelector(".widget-control");
            const iconWrap = head.querySelector(".alm-workspace-shortcut-icon");
            const pillInControl = control && control.querySelector(".indicator-pill");

            if (iconWrap) {
                let badge = iconWrap.querySelector(".alm-workspace-shortcut-badge");
                if (!badge) {
                    badge = document.createElement("span");
                    badge.className = "alm-workspace-shortcut-badge";
                    iconWrap.appendChild(badge);
                }
                if (pillInControl && !badge.contains(pillInControl)) {
                    badge.querySelectorAll(".indicator-pill").forEach((node) => node.remove());
                    badge.appendChild(pillInControl);
                }
            }

            if (control) {
                control.querySelectorAll("svg").forEach((svg) => {
                    if (!arrowHost.contains(svg)) arrowHost.appendChild(svg);
                });
            }
        });
    }

    function watchBreadcrumbs(page) {
        const crumbs = page.querySelector(".navbar-breadcrumbs");
        if (!crumbs) return;
        normalizeWorkspaceTrail(crumbs);
        if (breadcrumbObserver) return;
        breadcrumbObserver = trackObserver(new MutationObserver(() => {
            window.requestAnimationFrame(() => normalizeWorkspaceTrail(crumbs));
        }));
        breadcrumbObserver.observe(crumbs, { childList: true, subtree: true });
    }

    function enhancePageHead() {
        const page = workspacePage();
        if (!page) return;
        watchBreadcrumbs(page);
    }

    function enhanceShortcuts(root) {
        root.querySelectorAll(".shortcut-widget-box").forEach((widget) => {
            const linkTo = shortcutLinkTo(widget);
            const meta = shortcutMeta(linkTo);
            if (!meta || !linkTo) return;

            widget.classList.add(SHORTCUT_CLASS);
            widget.setAttribute("data-alm-link-to", linkTo);

            const labelWrap = widget.querySelector(".widget-label");
            if (!labelWrap) return;

            if (!labelWrap.querySelector(".alm-workspace-shortcut-desc") && meta.desc) {
                const desc = document.createElement("span");
                desc.className = "alm-workspace-shortcut-desc";
                desc.textContent = __(meta.desc);
                labelWrap.appendChild(desc);
            }

            const section = widget.getAttribute("data-alm-section");
            const head = widget.querySelector(".widget-head");
            const iconName = resolveShortcutIcon(section, meta);
            ensureShortcutIcon(head, iconName);
        });
    }

    function clearPolishMarks(root) {
        if (!root) return;
        root.removeAttribute(POLISH_FLAG);
        root.querySelectorAll(".alm-workspace-shortcut-desc").forEach((node) => node.remove());
        root.querySelectorAll(".alm-workspace-shortcut-icon").forEach((node) => node.remove());
        root.querySelectorAll(".alm-workspace-shortcut-arrow").forEach((node) => node.remove());
        root.querySelectorAll(".alm-workspace-shortcut-badge").forEach((node) => node.remove());
        root.querySelectorAll(".alm-workspace-section-meta").forEach((node) => node.remove());
        root.querySelectorAll(".widget.header[data-alm-section]").forEach((node) => {
            node.removeAttribute("data-alm-section");
        });
        root.querySelectorAll(`.shortcut-widget-box.${SHORTCUT_CLASS}`).forEach((node) => {
            node.classList.remove(SHORTCUT_CLASS);
        });
        root.querySelectorAll(".shortcut-widget-box[data-alm-section]").forEach((node) => {
            node.removeAttribute("data-alm-section");
        });
        root.querySelectorAll(".shortcut-widget-box[data-alm-link-to]").forEach((node) => {
            node.removeAttribute("data-alm-link-to");
        });
        root.querySelectorAll(".alm-workspace-shortcut-icon[data-alm-icon]").forEach((node) => {
            node.removeAttribute("data-alm-icon");
        });
        root.querySelectorAll(".alm-workspace-section-head").forEach((node) => {
            node.classList.remove("alm-workspace-section-head");
        });
    }

    function ensureRootObserver(root) {
        if (rootObserver || !root) return;
        rootObserver = trackObserver(new MutationObserver(() => schedule()));
        rootObserver.observe(root, { childList: true, subtree: true });
        root.setAttribute(POLISH_FLAG, "1");
    }

    function waitForEditorRoot(page) {
        if (editorRoot() || pageWaitObserver || !page) return;
        pageWaitObserver = trackObserver(new MutationObserver(() => {
            if (!isTargetWorkspace()) return;
            if (editorRoot()) {
                if (pageWaitObserver) {
                    pageWaitObserver.disconnect();
                    observers.delete(pageWaitObserver);
                    pageWaitObserver = null;
                }
                schedule();
            }
        }));
        pageWaitObserver.observe(page, { childList: true, subtree: true });
    }

    function deactivate() {
        active = false;
        document.body.classList.remove(ROOT_CLASS);
        disposeObservers();
        const page = workspacePage();
        if (page) {
            normalizeWorkspaceTrail(page.querySelector(".navbar-breadcrumbs"));
            const root = page.querySelector(".editor-js-container");
            if (root) clearPolishMarks(root);
        }
    }

    function polish() {
        if (!isTargetWorkspace()) {
            if (active) deactivate();
            return;
        }

        active = true;
        document.body.classList.add(ROOT_CLASS);
        enhancePageHead();

        const root = editorRoot();
        if (!root) {
            waitForEditorRoot(workspacePage());
            return;
        }

        enhanceHeaders(root);
        assignShortcutSections(root);
        enhanceShortcuts(root);
        layoutShortcutControls(root);
        ensureRootObserver(root);
    }

    function schedule() {
        if (scheduledFrame !== null) return;
        const run = window.requestAnimationFrame || ((cb) => window.setTimeout(cb, 16));
        scheduledFrame = run(() => {
            scheduledFrame = null;
            polish();
        });
    }

    function bindLifecycle() {
        if (window.frappe && frappe.router && !frappe.router.__almdinaWorkspaceHomeUX) {
            frappe.router.__almdinaWorkspaceHomeUX = true;
            frappe.router.on("change", () => schedule());
        }
        if (window.jQuery && !window.__almdinaWorkspaceHomePageChange) {
            window.__almdinaWorkspaceHomePageChange = true;
            window.jQuery(document).on("page-change.almdinaWorkspaceHome", schedule);
        }
        window.addEventListener("almdina:permissions-updated", schedule);
        window.addEventListener("beforeunload", dispose);
    }

    function deskReady() {
        return Boolean(window.frappe && frappe.boot && frappe.router);
    }

    function boot() {
        if (!deskReady()) return;
        if (booted) {
            schedule();
            return;
        }
        booted = true;
        const frontend = frontendApi();
        if (frontend && typeof frontend.createLifecycleScope === "function") {
            lifecycle = frontend.createLifecycleScope();
        }
        bindLifecycle();
        schedule();
    }

    // Frappe Desk fires app_ready once boot + router exist — no polling.
    if (window.jQuery) {
        window.jQuery(document).on("app_ready.almdinaWorkspaceHome", boot);
    }
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", () => {
            if (deskReady()) boot();
        });
    } else if (deskReady()) {
        boot();
    }

    window.AlmdinaWorkspaceHomeUX = Object.freeze({
        WORKSPACE_SLUG,
        WORKSPACE_NAME,
        SECTION_PRESENTATION,
        SHORTCUT_BLOCK_TO_LINK,
        isTargetWorkspace,
        polish,
        schedule,
        dispose,
        slugify,
        shortcutLinkTo,
    });
})();
