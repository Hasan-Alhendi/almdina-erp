(() => {
    "use strict";

    const CONTROLLER_FIELD = "__almdinaDcoFormSidebarController";
    const HOST_CLASS = "almadina-dco-form-sidebar-host";
    const FULL_WIDTH_CLASS = "almadina-dco-form-sidebar-native-collapsed";
    const TOGGLE_SELECTOR = "[data-almdina-dco-sidebar-toggle=\"1\"]";
    const STORAGE_PREFIX = "almdina:dco-form-sidebar:v1";
    const DOCTYPE = "Door Cutting Order";
    const EVENT_NAMESPACE = ".almdinaDcoFormSidebar";

    function node(value) {
        if (!value) return null;
        return value.nodeType ? value : (value[0] && value[0].nodeType ? value[0] : null);
    }

    function pageRoot(frm) {
        return node(frm && frm.page && frm.page.wrapper) || node(frm && frm.wrapper);
    }

    function currentUser() {
        return String(
            (window.frappe && window.frappe.session && window.frappe.session.user)
            || (window.frappe && window.frappe.boot && window.frappe.boot.user && window.frappe.boot.user.name)
            || "Guest"
        ).trim() || "Guest";
    }

    function storageKey() {
        return `${STORAGE_PREFIX}:${encodeURIComponent(currentUser())}:${encodeURIComponent(DOCTYPE)}`;
    }

    const preferenceStore = Object.freeze({
        read() {
            try {
                return window.localStorage && window.localStorage.getItem(storageKey()) === "expanded";
            } catch (_error) {
                return false;
            }
        },
        write(expanded) {
            try {
                if (window.localStorage) {
                    window.localStorage.setItem(storageKey(), expanded ? "expanded" : "collapsed");
                }
            } catch (_error) {
                // Storage can be unavailable in private browsing; native UI still works.
            }
        },
    });

    function isMobile() {
        const utils = window.frappe && window.frappe.utils;
        return Boolean(
            utils
            && typeof utils.is_xs === "function"
            && typeof utils.is_sm === "function"
            && (utils.is_xs() || utils.is_sm())
        );
    }

    function sidebarWrapper(frm) {
        const nativeSidebar = frm && frm.sidebar && frm.sidebar.sidebar;
        if (nativeSidebar && typeof nativeSidebar.parent === "function") {
            return nativeSidebar.parent();
        }
        const root = pageRoot(frm);
        return root && window.jQuery ? window.jQuery(root).find(".layout-side-section") : null;
    }

    function nativeSidebarExpanded(frm) {
        const wrapper = sidebarWrapper(frm);
        if (!wrapper || !wrapper.length) return null;

        if (isMobile()) {
            const overlay = wrapper.find(".overlay-sidebar");
            return Boolean(overlay.length && overlay.hasClass("opened"));
        }
        return typeof wrapper.is === "function" ? wrapper.is(":visible") : null;
    }

    class DcoFormSidebarController {
        constructor(frm) {
            this.frm = frm;
            this.preferredExpanded = false;
            this.initialized = false;
            this.bound = false;
            this.disposed = false;
            this.handleNativeToggle = this.handleNativeToggle.bind(this);
            this.handleFormHide = this.dispose.bind(this);
        }

        mount() {
            const root = pageRoot(this.frm);
            if (!root) return this;
            if (!this.initialized) {
                this.preferredExpanded = preferenceStore.read();
                this.initialized = true;
            }
            this.bindLifecycle(root);
            this.ensureNativePreference();
            this.reconcile(root);
            return this;
        }

        refresh() {
            return this.mount();
        }

        bindLifecycle(root) {
            if (this.disposed) this.disposed = false;
            if (this.bound) return;
            const body = window.jQuery && window.jQuery(document.body);
            const wrapper = window.jQuery && window.jQuery(root);
            if (body) body.on(`toggleSidebar${EVENT_NAMESPACE}`, this.handleNativeToggle);
            if (wrapper) wrapper.on(`hide${EVENT_NAMESPACE}`, this.handleFormHide);
            this.bound = true;
        }

        dispose() {
            if (!this.bound) return;
            const body = window.jQuery && window.jQuery(document.body);
            const root = pageRoot(this.frm);
            const wrapper = window.jQuery && window.jQuery(root);
            if (body) body.off(`toggleSidebar${EVENT_NAMESPACE}`, this.handleNativeToggle);
            if (wrapper) wrapper.off(`hide${EVENT_NAMESPACE}`, this.handleFormHide);
            this.bound = false;
            this.disposed = true;
        }

        ensureNativePreference() {
            if (isMobile()) return;
            const actual = nativeSidebarExpanded(this.frm);
            if (actual === null || actual === this.preferredExpanded) return;
            this.toggleNativeSidebar();
        }

        toggleNativeSidebar() {
            const toolbar = this.frm && this.frm.toolbar;
            const wrapper = sidebarWrapper(this.frm);
            if (
                !toolbar
                || typeof toolbar.setup_sidebar_toggle !== "function"
                || !wrapper
                || !wrapper.length
            ) return false;
            toolbar.setup_sidebar_toggle(wrapper);
            return true;
        }

        handleNativeToggle() {
            if (window.cur_frm && window.cur_frm !== this.frm) return;
            this.syncPresentation(pageRoot(this.frm));
        }

        ensureToggleButton(root) {
            const wrapper = sidebarWrapper(this.frm);
            if (!wrapper || !wrapper.length) return null;
            let button = root.querySelector(TOGGLE_SELECTOR);
            if (!button && this.frm.page && typeof this.frm.page.add_action_icon === "function") {
                const created = this.frm.page.add_action_icon(
                    "panel-right",
                    () => this.toggleNativeSidebar(),
                    "almadina-dco-form-sidebar-toggle",
                    "إظهار اللوحة الجانبية"
                );
                button = node(created);
            }
            return button;
        }

        reconcile(root) {
            root.classList.add(HOST_CLASS);
            const button = this.ensureToggleButton(root);
            this.syncPresentation(root, button);
        }

        syncPresentation(root, button = null) {
            if (!root) return;
            const expanded = nativeSidebarExpanded(this.frm);
            const mobile = isMobile();
            root.classList.toggle(FULL_WIDTH_CLASS, !mobile && expanded === false);

            const toggle = button || root.querySelector(TOGGLE_SELECTOR);
            if (!toggle || expanded === null) return;
            toggle.classList.add("almadina-dco-form-sidebar-toggle");
            toggle.dataset.almdinaDcoSidebarToggle = "1";
            toggle.setAttribute("aria-expanded", String(expanded));
            const label = expanded ? "إخفاء اللوحة الجانبية" : "إظهار اللوحة الجانبية";
            toggle.setAttribute("aria-label", label);
            const previousLabel = toggle.getAttribute("data-almdina-dco-sidebar-tooltip");
            toggle.setAttribute("title", label);
            toggle.setAttribute("data-original-title", label);
            toggle.setAttribute("data-almdina-dco-sidebar-tooltip", label);
            if (window.jQuery && previousLabel !== label) {
                const $toggle = window.jQuery(toggle);
                if (typeof $toggle.tooltip === "function") {
                    $toggle.tooltip("dispose").tooltip({ delay: { show: 600, hide: 100 }, trigger: "hover" });
                }
            }
            if (!mobile) {
                this.preferredExpanded = expanded;
                preferenceStore.write(expanded);
            }
        }
    }

    function mount(frm) {
        if (!frm || frm.doctype !== DOCTYPE) return null;
        if (!frm[CONTROLLER_FIELD]) frm[CONTROLLER_FIELD] = new DcoFormSidebarController(frm);
        return frm[CONTROLLER_FIELD].mount();
    }

    window.AlmdinaDcoFormSidebarController = Object.freeze({ mount });

    frappe.ui.form.on(DOCTYPE, {
        onload_post_render(frm) { mount(frm); },
        refresh(frm) {
            if (frm[CONTROLLER_FIELD]) frm[CONTROLLER_FIELD].refresh();
            else mount(frm);
        },
    });
})();
