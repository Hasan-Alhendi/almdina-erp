frappe.pages["factory-production-settings"].on_page_load = function (wrapper) {
    "use strict";

    const FOUNDATION = "/assets/almdina_erp/js/frontend_foundation.js";
    const MODULES = Object.freeze([
        "/assets/almdina_erp/js/factory_production_settings/api.js",
        "/assets/almdina_erp/js/factory_production_settings/state.js",
        "/assets/almdina_erp/js/factory_production_settings/view_model.js",
        "/assets/almdina_erp/js/factory_production_settings/renderer.js",
        "/assets/almdina_erp/js/factory_production_settings/interactions.js",
        "/assets/almdina_erp/js/factory_production_settings/dialogs.js",
        "/assets/almdina_erp/js/factory_production_settings/controller.js",
    ]);
    const STYLESHEET = "/assets/almdina_erp/css/factory_production_settings.css";
    const $main = $(wrapper).find(".layout-main-section");

    function showBootstrapError(error) {
        const fallback = __("تعذر تحميل إعدادات المعمل.");
        const frontend = window.AlmdinaFrontend;
        const message = frontend && typeof frontend.errorMessage === "function"
            ? frontend.errorMessage(error, fallback)
            : String((error && error.message) || fallback);
        const safe = frappe.utils.escape_html(String(message || fallback));
        $main.html(`<div class="frappe-card" style="padding:24px;text-align:center">${safe}</div>`);
        frappe.show_alert({ message, indicator: "red" }, 7);
    }

    function ensureFoundation() {
        const current = window.AlmdinaFrontend;
        if (current && typeof current.ensureStylesheet === "function") {
            return Promise.resolve(current);
        }

        return Promise.resolve(frappe.require(FOUNDATION)).then(() => {
            const loaded = window.AlmdinaFrontend;
            if (!loaded || typeof loaded.ensureStylesheet !== "function") {
                throw new Error("Almdina frontend foundation did not initialize");
            }
            return loaded;
        });
    }

    return ensureFoundation()
        .then(frontend => {
            // Page scripts can win the race against app-level include evaluation on
            // a cold Desk load. Resolve the shared foundation first, then keep the
            // existing batched feature-module and stylesheet ownership unchanged.
            const moduleLoad = typeof frontend.requireAssets === "function"
                ? frontend.requireAssets(MODULES)
                : Promise.resolve(frappe.require(MODULES));
            const styleLoad = frontend.ensureStylesheet(STYLESHEET, {
                id: "almdina-production-settings-style",
            });
            return Promise.all([moduleLoad, styleLoad]);
        })
        .then(() => {
            const controller = window.AlmdinaFactoryProductionSettingsController;
            if (!controller || typeof controller.mount !== "function") {
                throw new Error("Production Settings controller did not initialize");
            }
            return controller.mount(wrapper);
        })
        .catch(showBootstrapError);
};
