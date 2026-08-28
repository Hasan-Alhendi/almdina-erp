(() => {
    "use strict";

    // Registered from both entry points: this file ships in `app_include_js`
    // before the document context exists and again in the DCO DocType bundle,
    // where the document context can own protected-surface recovery.
    function registerProtectedModuleSurface(api) {
        const documentContext = window.AlmdinaDocumentContext;
        if (
            !api
            || !documentContext
            || typeof documentContext.registerSurface !== "function"
            || typeof api.orderModulesLoaded !== "function"
            || typeof api.ensureOrderModules !== "function"
        ) {
            return false;
        }
        return documentContext.registerSurface("order-protected-modules", {
            isReady() { return api.orderModulesLoaded(); },
            recover() { return api.ensureOrderModules(); },
        });
    }

    if (window.AlmdinaPermissions) {
        registerProtectedModuleSurface(window.AlmdinaPermissions);
        return;
    }

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
        surfaces: Object.freeze({}),
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
        view_customers: "read",
        view_edge_banding_types: "read",
        create_edge_banding_types: "create",
        edit_edge_banding_types: "write",
        delete_edge_banding_types: "delete",
    });

    // Only security/navigation owners belong to the protected DCO bootstrap.
    // Plan and Cost presentation are feature assets and are loaded exclusively
    // by AlmdinaDcoWorkspaceAssetRegistry when their tabs become active.
    const ORDER_CORE_GLOBALS = Object.freeze([
        "AlmdinaOrderPermissionRefreshUX",
        "AlmdinaOrderTabPermissionsUX",
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

    function normalizeBooleanMap(raw) {
        const result = {};
        if (raw && typeof raw === "object") {
            Object.keys(raw).forEach(key => {
                result[String(key)] = raw[key] === true;
            });
        }
        return Object.freeze(result);
    }

    function normalize(raw) {
        if (!raw || typeof raw !== "object") return EMPTY_CONTEXT;
        const navigation = normalizeNavigation(raw.navigation);
        return Object.freeze({
            version: Number.isFinite(Number(raw.version)) ? Number(raw.version) : 0,
            profile: String(raw.profile || navigation.profile || "shared"),
            capabilities: normalizeBooleanMap(raw.capabilities),
            navigation,
            surfaces: normalizeBooleanMap(raw.surfaces),
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

    function nativeDocumentNarrowingAllows(frm, capability) {
        const key = String(capability || "");
        if (!Object.prototype.hasOwnProperty.call(STANDARD_CAPABILITY_PERMISSION_TYPES, key)) {
            return true;
        }
        return nativeDocumentPermission(frm, key);
    }

    let context = normalize(frappe.boot && frappe.boot.almdina_permissions);
    let refreshPromise = null;

    function emitUpdatedContext() {
        window.dispatchEvent(
            new CustomEvent("almdina:permissions-updated", { detail: context })
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

        refreshPromise = Promise.resolve(
            frappe.call({
                method: "almdina_erp.almdina_erp.services.permission_context_service.get_permission_context",
            })
        )
            .then(response => {
                context = normalize(response && response.message);
                emitUpdatedContext();
                return context;
            })
            .finally(() => {
                refreshPromise = null;
            });
        return refreshPromise;
    }

    function orderModulesLoaded() {
        return ORDER_CORE_GLOBALS.every(name => Boolean(window[name]));
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

    function ensureOrderModules() {
        if (!window.cur_frm || window.cur_frm.doctype !== "Door Cutting Order") {
            return Promise.resolve(false);
        }
        // The DCO DocType manifest owns these core modules. Do not poll or load
        // Plan/Cost compatibility assets from the global permission layer.
        if (!orderModulesLoaded()) return Promise.resolve(false);
        return recoverCurrentOrderSurface();
    }

    const permissions = Object.freeze({
        can(capability) {
            return context.capabilities[String(capability || "")] === true;
        },
        canDocument(frm, capability) {
            const key = String(capability || "");
            if (context.capabilities[key] !== true) return false;
            return nativeDocumentNarrowingAllows(frm, key);
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
        surface(surfaceName) {
            return context.surfaces[String(surfaceName || "")] === true;
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
            return ensureOrderModules();
        },
        orderModulesLoaded() {
            return orderModulesLoaded();
        },
        ensureOrderModules() {
            return ensureOrderModules();
        },
    });

    window.AlmdinaPermissions = permissions;
    frappe.provide("frappe.almdina");
    frappe.almdina.permissions = permissions;

    registerProtectedModuleSurface(permissions);

    // A later visit to DCO may happen long after Desk boot. The router only asks
    // the already-loaded DCO core to reconcile permissions; it never imports a
    // feature bundle and never polls for globals.
    if (
        window.frappe
        && frappe.router
        && typeof frappe.router.on === "function"
        && !frappe.router.__almdinaPermissionModules
    ) {
        frappe.router.__almdinaPermissionModules = true;
        frappe.router.on("change", () => {
            window.setTimeout(ensureOrderModules, 0);
        });
    }

    window.setTimeout(ensureOrderModules, 0);
})();
