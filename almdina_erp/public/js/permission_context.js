(() => {
    "use strict";

    const EMPTY_NAVIGATION = Object.freeze({
        shared_shell: false,
        app_only: false,
        profile: "shared",
        home_page: "",
        default_route: "",
        workspaces: Object.freeze([]),
        sections: Object.freeze({}),
    });

    const EMPTY_CONTEXT = Object.freeze({
        version: 0,
        profile: "shared",
        capabilities: Object.freeze({}),
        navigation: EMPTY_NAVIGATION,
    });

    const STANDARD_CAPABILITY_PERMISSION_TYPES = Object.freeze({
        view_orders: "read",
        create_order: "create",
        edit_order: "write",
        view_factory_settings: "read",
        view_production_routings: "read",
        create_production_routings: "create",
        edit_production_routings: "write",
        delete_production_routings: "delete",
        view_edge_banding_types: "read",
        create_edge_banding_types: "create",
        edit_edge_banding_types: "write",
        delete_edge_banding_types: "delete",
    });

    const ORDER_MODULES = Object.freeze([
        Object.freeze({
            path: "/assets/almdina_erp/js/door_cutting_order_cost_presenter.js",
            global: "AlmdinaOrderCostUX",
        }),
        Object.freeze({
            path: "/assets/almdina_erp/js/door_cutting_order_permission_refresh_ux.js",
            global: "AlmdinaOrderPermissionRefreshUX",
        }),
        Object.freeze({
            path: "/assets/almdina_erp/js/door_cutting_order_tab_permissions_ux.js",
            global: "AlmdinaOrderTabPermissionsUX",
        }),
        Object.freeze({
            path: "/assets/almdina_erp/js/door_cutting_order_customer_invoice_toolbar_ux.js",
            global: "AlmdinaCustomerInvoiceToolbarUX",
        }),
    ]);

    function normalizeNavigation(raw) {
        if (!raw || typeof raw !== "object") return EMPTY_NAVIGATION;
        const sections = {};
        const sourceSections = raw.sections;
        if (sourceSections && typeof sourceSections === "object") {
            Object.keys(sourceSections).forEach(section => {
                sections[String(section)] = sourceSections[section] === true;
            });
        }
        const workspaces = Array.isArray(raw.workspaces)
            ? raw.workspaces.map(value => String(value || "")).filter(Boolean)
            : [];
        return Object.freeze({
            shared_shell: raw.shared_shell === true,
            app_only: raw.app_only === true,
            profile: String(raw.profile || "shared"),
            home_page: String(raw.home_page || ""),
            default_route: String(raw.default_route || ""),
            workspaces: Object.freeze(workspaces),
            sections: Object.freeze(sections),
        });
    }

    function normalize(raw) {
        if (!raw || typeof raw !== "object") return EMPTY_CONTEXT;

        const source = raw.capabilities;
        const capabilities = {};
        if (source && typeof source === "object") {
            Object.keys(source).forEach(capability => {
                capabilities[String(capability)] = source[capability] === true;
            });
        }
        const navigation = normalizeNavigation(raw.navigation);

        return Object.freeze({
            version: Number.isFinite(Number(raw.version)) ? Number(raw.version) : 0,
            profile: String(raw.profile || navigation.profile || "shared"),
            capabilities: Object.freeze(capabilities),
            navigation,
        });
    }

    function requestedCapabilities(values) {
        const flattened = values.flat ? values.flat(Infinity) : values;
        return flattened.map(value => String(value || "")).filter(Boolean);
    }

    function permissionTypeFor(capability) {
        const key = String(capability || "");
        return STANDARD_CAPABILITY_PERMISSION_TYPES[key] || key;
    }

    function nativeDocumentPermission(frm, capability) {
        if (!frm || typeof frm.has_perm !== "function") return false;
        try {
            return Boolean(frm.has_perm(permissionTypeFor(capability)));
        } catch (error) {
            console.debug("Could not resolve native document permission", error);
            return false;
        }
    }

    let context = normalize(frappe.boot && frappe.boot.almdina_permissions);
    let refreshPromise = null;
    let modulesPromise = null;

    function emitUpdatedContext() {
        window.dispatchEvent(
            new CustomEvent("almdina:permissions-updated", {
                detail: context,
            })
        );
    }

    function refreshContext() {
        if (!window.frappe || typeof frappe.call !== "function") {
            return Promise.resolve(context);
        }
        if (frappe.session && frappe.session.user === "Guest") {
            return Promise.resolve(context);
        }
        if (refreshPromise) return refreshPromise;

        refreshPromise = frappe.call({
            method: "almdina_erp.almdina_erp.services.permission_context_service.get_permission_context",
        }).then(response => {
            context = normalize(response && response.message);
            emitUpdatedContext();
            return context;
        }).finally(() => {
            refreshPromise = null;
        });

        return refreshPromise;
    }

    function globalExists(name) {
        return Boolean(name && window[name]);
    }

    function waitForGlobal(name, timeoutMs = 12000) {
        if (globalExists(name)) return Promise.resolve(window[name]);

        return new Promise((resolve, reject) => {
            const started = Date.now();
            const timer = window.setInterval(() => {
                if (globalExists(name)) {
                    window.clearInterval(timer);
                    resolve(window[name]);
                    return;
                }
                if (Date.now() - started >= timeoutMs) {
                    window.clearInterval(timer);
                    reject(new Error(`Timed out loading ${name}`));
                }
            }, 50);
        });
    }

    function requireModule(module) {
        if (globalExists(module.global)) {
            return Promise.resolve(window[module.global]);
        }
        try {
            frappe.require(module.path);
        } catch (error) {
            return Promise.reject(error);
        }
        return waitForGlobal(module.global);
    }

    function recoverCurrentOrderSurface() {
        const frm = window.cur_frm;
        const recovery = window.AlmdinaOrderPermissionRefreshUX;
        if (
            !frm
            || frm.doctype !== "Door Cutting Order"
            || !recovery
            || typeof recovery.refreshPermissions !== "function"
        ) {
            return Promise.resolve(false);
        }
        return Promise.resolve(recovery.refreshPermissions(frm));
    }

    function loadOrderModules() {
        if (modulesPromise) return modulesPromise;
        if (
            !window.frappe
            || typeof frappe.require !== "function"
            || !frappe.ui
            || !frappe.ui.form
            || typeof frappe.ui.form.on !== "function"
        ) {
            return null;
        }

        modulesPromise = ORDER_MODULES.reduce(
            (promise, module) => promise.then(() => requireModule(module)),
            Promise.resolve()
        ).then(() => recoverCurrentOrderSurface())
            .catch(error => {
                modulesPromise = null;
                console.error("Failed to load Almdina protected order modules", error);
                throw error;
            });
        return modulesPromise;
    }

    const permissions = Object.freeze({
        can(capability) {
            return context.capabilities[String(capability || "")] === true;
        },
        canDocument(frm, capability) {
            const key = String(capability || "");
            return context.capabilities[key] === true
                || nativeDocumentPermission(frm, key);
        },
        permissionType(capability) {
            return permissionTypeFor(capability);
        },
        any(...capabilities) {
            return requestedCapabilities(capabilities).some(capability => this.can(capability));
        },
        all(...capabilities) {
            const requested = requestedCapabilities(capabilities);
            return requested.length > 0 && requested.every(capability => this.can(capability));
        },
        section(sectionName) {
            return context.navigation.sections[String(sectionName || "")] === true;
        },
        profile() {
            return context.profile;
        },
        navigation() {
            return context.navigation;
        },
        home() {
            return context.navigation.home_page;
        },
        workspaces() {
            return context.navigation.workspaces.slice();
        },
        version() {
            return context.version;
        },
        snapshot() {
            return context;
        },
        refresh() {
            return refreshContext();
        },
        loadOrderModules() {
            return loadOrderModules();
        },
    });

    window.AlmdinaPermissions = permissions;
    frappe.provide("frappe.almdina");
    frappe.almdina.permissions = permissions;

    let attempts = 0;
    const timer = window.setInterval(() => {
        attempts += 1;
        const loading = loadOrderModules();
        if (loading || attempts >= 100) {
            window.clearInterval(timer);
        }
    }, 100);
})();
