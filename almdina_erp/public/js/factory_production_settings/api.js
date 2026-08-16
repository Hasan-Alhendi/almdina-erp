(() => {
    "use strict";

    if (window.AlmdinaFactoryProductionSettingsApi) return;

    const BASE = "almdina_erp.almdina_erp.services.production_settings_service";
    const METHODS = Object.freeze({
        get: `${BASE}.get_production_settings`,
        update: `${BASE}.update_production_settings`,
        audit: `${BASE}.get_factory_settings_audit`,
    });

    function foundation() {
        const api = window.AlmdinaFrontend;
        if (!api || typeof api.rpc !== "function") {
            throw new Error("Almdina frontend foundation is unavailable");
        }
        return api;
    }

    function request(method, args = {}, options = {}) {
        return foundation().rpc(method, args, options);
    }

    function getSettings(options = {}) {
        return request(METHODS.get, {}, options).then(data => data || {});
    }

    function updateSettings(values, options = {}) {
        return request(
            METHODS.update,
            { values: JSON.stringify(values || {}) },
            options
        ).then(data => data || {});
    }

    function getAudit(options = {}) {
        return request(METHODS.audit, { limit: 50 }, options).then(rows => (
            Array.isArray(rows) ? rows : []
        ));
    }

    window.AlmdinaFactoryProductionSettingsApi = Object.freeze({
        getSettings,
        updateSettings,
        getAudit,
    });
})();
