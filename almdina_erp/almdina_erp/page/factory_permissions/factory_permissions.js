frappe.pages["factory-permissions"].on_page_load = function (wrapper) {
    "use strict";

    const FOUNDATION = "/assets/almdina_erp/js/frontend_foundation.js";
    const MODULES = Object.freeze([
        "/assets/almdina_erp/js/factory_permissions/api.js",
        "/assets/almdina_erp/js/factory_permissions/state.js",
        "/assets/almdina_erp/js/factory_permissions/view_model.js",
        "/assets/almdina_erp/js/factory_permissions/renderer.js",
        "/assets/almdina_erp/js/factory_permissions/interactions.js",
        "/assets/almdina_erp/js/factory_permissions/controller.js",
    ]);
    const STYLESHEET = "/assets/almdina_erp/css/factory_permissions.css";
    const $main = $(wrapper).find(".layout-main-section");

    function showBootstrapError(error) {
        const fallback = __("تعذر تحميل واجهة إدارة الصلاحيات.");
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
            // Frappe can execute a Page entry before app-level include assets have
            // finished evaluating. Make this composition root self-sufficient so
            // a cold Desk navigation never depends on that global timing race.
            const moduleLoad = typeof frontend.requireAssets === "function"
                ? frontend.requireAssets(MODULES)
                : Promise.resolve(frappe.require(MODULES));
            const styleLoad = frontend.ensureStylesheet(STYLESHEET, {
                id: "almdina-permission-console-style",
            });
            return Promise.all([moduleLoad, styleLoad]);
        })
        .then(() => {
            const controller = window.AlmdinaFactoryPermissionsController;
            if (!controller || typeof controller.mount !== "function") {
                throw new Error("Factory permissions controller did not initialize");
            }
            return controller.mount(wrapper);
        })
        .catch(showBootstrapError);
};
