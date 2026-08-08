(() => {
    "use strict";

    if (window.__almdinaPermissionActionVisibilityGuard) return;
    window.__almdinaPermissionActionVisibilityGuard = true;

    let observer = null;
    let timer = null;

    function permissions() {
        return window.AlmdinaPermissions || null;
    }

    function can(capability) {
        const api = permissions();
        return Boolean(api && typeof api.can === "function" && api.can(capability));
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

    function buttonText(button) {
        return String(button && button.textContent || "").replace(/\s+/g, " ").trim();
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
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", start, { once: true });
    } else {
        start();
    }
})();
