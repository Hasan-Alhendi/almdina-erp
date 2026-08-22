frappe.pages["factory-permissions"].on_page_load = function (wrapper) {
    "use strict";

    const MODULES = Object.freeze([
        "/assets/almdina_erp/js/factory_permissions/api.js",
        "/assets/almdina_erp/js/factory_permissions/state.js",
        "/assets/almdina_erp/js/factory_permissions/view_model.js",
        "/assets/almdina_erp/js/factory_permissions/renderer.js",
        "/assets/almdina_erp/js/factory_permissions/interactions.js",
        "/assets/almdina_erp/js/factory_permissions/controller.js",
    ]);
    const STYLESHEET = "/assets/almdina_erp/css/factory_permissions.css";
    const frontend = window.AlmdinaFrontend;
    const $main = $(wrapper).find(".layout-main-section");

    function showBootstrapError(error) {
        const fallback = __("تعذر تحميل واجهة إدارة الصلاحيات.");
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

    // Page scripts and app-level assets are cached independently by Frappe/Desk.
    // During a deploy the Page can therefore be newer than the cached foundation.
    // Prefer the shared loader, but retain one native batched require as a
    // compatibility path so deploy skew never blocks the permissions console.
    const moduleLoad = typeof frontend.requireAssets === "function"
        ? frontend.requireAssets(MODULES)
        : Promise.resolve(frappe.require(MODULES));
    const styleLoad = frontend.ensureStylesheet(STYLESHEET, {
        id: "almdina-permission-console-style",
    });

    Promise.all([moduleLoad, styleLoad])
        .then(() => {
            const controller = window.AlmdinaFactoryPermissionsController;
            if (!controller || typeof controller.mount !== "function") {
                throw new Error("Factory permissions controller did not initialize");
            }
            controller.mount(wrapper);
        })
        .catch(showBootstrapError);
};
