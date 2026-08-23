frappe.pages["factory-workforce"].on_page_load = function (wrapper) {
    "use strict";

    const FOUNDATION = "/assets/almdina_erp/js/frontend_foundation.js";
    const MODULES = Object.freeze([
        "/assets/almdina_erp/js/factory_workforce/api.js",
        "/assets/almdina_erp/js/factory_workforce/state.js",
        "/assets/almdina_erp/js/factory_workforce/view_model.js",
        "/assets/almdina_erp/js/factory_workforce/renderer.js",
        "/assets/almdina_erp/js/factory_workforce/interactions.js",
        "/assets/almdina_erp/js/factory_workforce/dialogs.js",
        "/assets/almdina_erp/js/factory_workforce/controller.js",
    ]);
    const STYLESHEET = "/assets/almdina_erp/css/factory_workforce.css";
    const $main = $(wrapper).find(".layout-main-section");

    function showBootstrapError(error) {
        const fallback = __("تعذر تحميل واجهة المستخدمين والقوى العاملة.");
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
            // Cold Desk navigation can evaluate this Page before app-level include
            // assets finish. Bootstrap the shared foundation on demand instead of
            // treating that transient ordering as a permanent page failure.
            const moduleLoad = typeof frontend.requireAssets === "function"
                ? frontend.requireAssets(MODULES)
                : Promise.resolve(frappe.require(MODULES));
            const styleLoad = frontend.ensureStylesheet(STYLESHEET, {
                id: "almdina-workforce-console-style",
            });
            return Promise.all([moduleLoad, styleLoad]);
        })
        .then(() => {
            const controller = window.AlmdinaFactoryWorkforceController;
            if (!controller || typeof controller.mount !== "function") {
                throw new Error("Factory workforce controller did not initialize");
            }
            return controller.mount(wrapper);
        })
        .catch(showBootstrapError);
};
