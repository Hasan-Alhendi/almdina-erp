(() => {
    "use strict";

    const CONTROLLER_FIELD = "__almdinaDcoFormSidebarController";
    const HOST_CLASS = "almadina-dco-form-sidebar-host";
    const COLLAPSED_CLASS = "almadina-dco-form-sidebar-collapsed";
    const TOGGLE_SELECTOR = "[data-almdina-dco-sidebar-toggle=\"1\"]";
    const STORAGE_PREFIX = "almdina:dco-form-sidebar:v1";
    const DOCTYPE = "Door Cutting Order";

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
                // Storage can be unavailable in private browsing; UI state still works.
            }
        },
    });

    class DcoFormSidebarController {
        constructor(frm) {
            this.frm = frm;
            this.expanded = false;
            this.initialized = false;
        }

        mount() {
            const root = pageRoot(this.frm);
            if (!root) return this;
            if (!this.initialized) {
                this.expanded = preferenceStore.read();
                this.initialized = true;
            }
            this.reconcile(root);
            return this;
        }

        refresh() {
            return this.mount();
        }

        toggle() {
            this.expanded = !this.expanded;
            preferenceStore.write(this.expanded);
            this.refresh();
        }

        reconcile(root) {
            root.classList.add(HOST_CLASS);
            root.classList.toggle(COLLAPSED_CLASS, !this.expanded);

            let button = root.querySelector(TOGGLE_SELECTOR);
            if (!button && this.frm.page && typeof this.frm.page.add_action_icon === "function") {
                const created = this.frm.page.add_action_icon(
                    "panel-right",
                    () => {},
                    "almadina-dco-form-sidebar-toggle",
                    "إظهار اللوحة الجانبية"
                );
                button = node(created);
                // Page.add_action_icon binds the supplied callback; remove the
                // placeholder binding so this controller owns one real handler.
                if (button && window.jQuery) window.jQuery(button).off("click");
            }
            if (!button) return;

            button.classList.add("almadina-dco-form-sidebar-toggle");
            button.dataset.almdinaDcoSidebarToggle = "1";
            if (!button.__almadinaDcoSidebarBound) {
                button.addEventListener("click", event => {
                    event.preventDefault();
                    this.toggle();
                });
                button.__almadinaDcoSidebarBound = true;
            }
            button.setAttribute("aria-expanded", String(this.expanded));
            button.setAttribute("aria-label", this.expanded ? "إخفاء اللوحة الجانبية" : "إظهار اللوحة الجانبية");
            button.setAttribute("title", this.expanded ? "إخفاء اللوحة الجانبية" : "إظهار اللوحة الجانبية");
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
