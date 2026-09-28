(() => {
    "use strict";

    if (window.AlmdinaWorkspaceHomeUX) return;

    const WORKSPACE_SLUG = "almdina-erp";
    const WORKSPACE_NAME = "Almdina ERP";
    const WORKSPACE_PAGE_TITLE = "إدارة المعمل";
    const ROOT_CLASS = "almdina-workspace-home";
    const POLISH_FLAG = "data-almdina-workspace-home-polish";

    const presentationApi = () => window.AlmdinaShortcutPresentation || null;

    const SECTION_PRESENTATION = Object.freeze({
        "الإعدادات الأساسية": { id: "master", meta: "3 وحدات رئيسية" },
        "إدارة النظام ومسارات العمل": { id: "system", meta: "4 وحدات" },
        "التشغيل اليومي": { id: "ops", meta: "سير عمل الصالة والمعمل" },
        "التقارير التشغيلية والتكلفة": { id: "reports", meta: "البيانات الإحصائية والتحليلية" },
    });

    let observer = null;
    let breadcrumbObserver = null;
    let scheduledFrame = null;
    let booted = false;
    let missingRootAttempts = 0;

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

    function editorRoot() {
        const page = document.getElementById("page-Workspaces");
        if (page) {
            const scoped = page.querySelector(".editor-js-container");
            if (scoped) return scoped;
        }
        return document.querySelector(".layout-main-section .editor-js-container");
    }

    function sectionKeyFromHeader(headerWidget) {
        const text = normalizeText(headerWidget.textContent);
        return Object.keys(SECTION_PRESENTATION).find((key) => text.includes(key)) || "";
    }

    function shortcutLabel(widget) {
        const title = widget.querySelector(".widget-title");
        return normalizeText(title && title.textContent);
    }

    function renderIcon(name) {
        const api = presentationApi();
        if (api) return api.renderIcon(name, "md");
        if (window.frappe && frappe.utils && typeof frappe.utils.icon === "function") {
            return frappe.utils.icon(name, "md");
        }
        return "";
    }

    function shortcutMeta(label) {
        const api = presentationApi();
        return api ? api.metaForLabel(label) : null;
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

    function watchShortcutControl(widget, root) {
        if (widget.getAttribute("data-alm-control-watch") === "1") return;
        const control = widget.querySelector(".widget-control");
        if (!control) return;
        const observer = new MutationObserver(() => layoutShortcutControls(root));
        observer.observe(control, { childList: true, subtree: true });
        widget.setAttribute("data-alm-control-watch", "1");
    }

    function enhanceHeaders(root) {
        root.querySelectorAll(".widget.header").forEach((header) => {
            const key = sectionKeyFromHeader(header);
            if (!key) return;
            const presentation = SECTION_PRESENTATION[key];
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
                const key = sectionKeyFromHeader(header);
                if (key) currentSection = SECTION_PRESENTATION[key].id;
                return;
            }
            const widget = block.querySelector(".shortcut-widget-box");
            if (widget && currentSection) {
                widget.setAttribute("data-alm-section", currentSection);
            }
        });
    }

    function workspacePage() {
        return document.getElementById("page-Workspaces");
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
            const pillInControl = control?.querySelector(".indicator-pill");

            if (iconWrap) {
                let badge = iconWrap.querySelector(".alm-workspace-shortcut-badge");
                if (!badge) {
                    badge = document.createElement("span");
                    badge.className = "alm-workspace-shortcut-badge";
                    iconWrap.appendChild(badge);
                }
                if (pillInControl) {
                    badge.querySelectorAll(".indicator-pill").forEach((node) => node.remove());
                    badge.appendChild(pillInControl);
                }
            }

            if (control) {
                control.querySelectorAll("svg").forEach((svg) => {
                    if (!arrowHost.contains(svg)) arrowHost.appendChild(svg);
                });
            }

            watchShortcutControl(widget, root);
        });
    }

    function watchBreadcrumbs(page) {
        const crumbs = page.querySelector(".navbar-breadcrumbs");
        if (!crumbs) return;
        normalizeWorkspaceTrail(crumbs);
        if (breadcrumbObserver) return;
        breadcrumbObserver = new MutationObserver(() => {
            window.requestAnimationFrame(() => normalizeWorkspaceTrail(crumbs));
        });
        breadcrumbObserver.observe(crumbs, { childList: true, subtree: true });
    }

    function enhancePageHead() {
        const page = workspacePage();
        if (!page) return;
        watchBreadcrumbs(page);
    }

    function enhanceShortcuts(root) {
        root.querySelectorAll(".shortcut-widget-box").forEach((widget) => {
            const label = shortcutLabel(widget);
            const meta = shortcutMeta(label);
            if (!meta) return;

            const labelWrap = widget.querySelector(".widget-label");
            if (!labelWrap) return;

            if (!labelWrap.querySelector(".alm-workspace-shortcut-desc")) {
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
        root.querySelectorAll(".shortcut-widget-box[data-alm-control-watch]").forEach((node) => {
            node.removeAttribute("data-alm-control-watch");
        });
        root.querySelectorAll(".shortcut-widget-box[data-alm-section]").forEach((node) => {
            node.removeAttribute("data-alm-section");
        });
        root.querySelectorAll(".alm-workspace-shortcut-icon[data-alm-icon]").forEach((node) => {
            node.removeAttribute("data-alm-icon");
        });
        root.querySelectorAll(".alm-workspace-section-head").forEach((node) => {
            node.classList.remove("alm-workspace-section-head");
        });
    }

    function polish() {
        const active = isTargetWorkspace();
        document.body.classList.toggle(ROOT_CLASS, active);
        if (!active) {
            missingRootAttempts = 0;
            if (observer) observer.disconnect();
            observer = null;
            if (breadcrumbObserver) breadcrumbObserver.disconnect();
            breadcrumbObserver = null;
            const page = workspacePage();
            if (page) {
                normalizeWorkspaceTrail(page.querySelector(".navbar-breadcrumbs"));
            }
            return;
        }

        enhancePageHead();

        const root = editorRoot();
        if (!root) {
            if (missingRootAttempts < 40) {
                missingRootAttempts += 1;
                window.setTimeout(schedule, 120);
            }
            return;
        }
        missingRootAttempts = 0;

        enhanceHeaders(root);
        assignShortcutSections(root);
        enhanceShortcuts(root);
        layoutShortcutControls(root);

        if (root.getAttribute(POLISH_FLAG) !== "1") {
            root.setAttribute(POLISH_FLAG, "1");
            if (!observer) {
                observer = new MutationObserver(() => schedule());
                observer.observe(root, { childList: true, subtree: true });
            }
        }
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
    }

    function deskReady() {
        return Boolean(window.frappe && frappe.boot && frappe.router);
    }

    function boot() {
        if (booted) {
            schedule();
            return;
        }
        if (!deskReady()) return;
        booted = true;
        bindLifecycle();
        schedule();
    }

    function waitForDesk(attempt) {
        boot();
        if (booted || attempt >= 120) return;
        window.setTimeout(() => waitForDesk(attempt + 1), 100);
    }

    if (window.jQuery) {
        window.jQuery(document).on("app_ready.almdinaWorkspaceHome", () => waitForDesk(0));
    }
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", () => waitForDesk(0));
    } else {
        waitForDesk(0);
    }

    window.AlmdinaWorkspaceHomeUX = Object.freeze({
        WORKSPACE_SLUG,
        WORKSPACE_NAME,
        isTargetWorkspace,
        polish,
        schedule,
        slugify,
    });
})();
