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

    const context = normalize(frappe.boot && frappe.boot.almdina_permissions);
    const permissions = Object.freeze({
        can(capability) {
            return context.capabilities[String(capability || "")] === true;
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
    });

    window.AlmdinaPermissions = permissions;
    frappe.provide("frappe.almdina");
    frappe.almdina.permissions = permissions;
})();
