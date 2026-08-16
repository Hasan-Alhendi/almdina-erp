frappe.pages["factory-production-settings"].on_page_load = function (wrapper) {
    "use strict";

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
    const frontend = window.AlmdinaFrontend;
    const $main = $(wrapper).find(".layout-main-section");

    function showBootstrapError(error) {
        const fallback = __("تعذر تحميل إعدادات المعمل.");
        const message = frontend && typeof frontend.errorMessage === "function"
            ? frontend.errorMessage(error, fallback)
            : fallback;
        const safe = frappe.utils.escape_html(String(message || fallback));
        $main.html(`<div class="frappe-card" style="padding:24px;text-align:center">${safe}</div>`);
        frappe.show_alert({ message, indicator: "red" }, 7);
    }

    if (!frontend || typeof frontend.ensureStylesheet !== "function") {
        showBootstrapError(new Error("Almdina frontend foundation is unavailable"));
        return;
    }
    if (typeof frappe.require !== "function") {
        showBootstrapError(new Error("Frappe asset loader is unavailable"));
        return;
    }

    const moduleLoad = MODULES.reduce(
        (promise, asset) => promise.then(() => Promise.resolve(frappe.require(asset))),
        Promise.resolve()
    );
    const styleLoad = frontend.ensureStylesheet(STYLESHEET, {
        id: "almdina-production-settings-style",
    });

    Promise.all([moduleLoad, styleLoad])
        .then(() => {
            const controller = window.AlmdinaFactoryProductionSettingsController;
            if (!controller || typeof controller.mount !== "function") {
                throw new Error("Production Settings controller did not initialize");
            }
            controller.mount(wrapper);
        })
        .catch(showBootstrapError);
};
