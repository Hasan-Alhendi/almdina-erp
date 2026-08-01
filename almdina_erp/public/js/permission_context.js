(() => {
    "use strict";

    const EMPTY_CONTEXT = Object.freeze({
        version: 0,
        profile: "full",
        capabilities: Object.freeze({}),
    });

    function normalize(raw) {
        if (!raw || typeof raw !== "object") return EMPTY_CONTEXT;

        const source = raw.capabilities;
        const capabilities = {};
        if (source && typeof source === "object") {
            Object.keys(source).forEach(capability => {
                capabilities[String(capability)] = source[capability] === true;
            });
        }

        return Object.freeze({
            version: Number.isFinite(Number(raw.version)) ? Number(raw.version) : 0,
            profile: String(raw.profile || "full"),
            capabilities: Object.freeze(capabilities),
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
        profile() {
            return context.profile;
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
