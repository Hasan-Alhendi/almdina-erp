frappe.pages["factory-workforce"].on_page_load = function (wrapper) {
    "use strict";

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
    const frontend = window.AlmdinaFrontend;
    const $main = $(wrapper).find(".layout-main-section");

    function showBootstrapError(error) {
        const fallback = __("تعذر تحميل واجهة المستخدمين والقوى العاملة.");
        const message = frontend && typeof frontend.errorMessage === "function"
            ? frontend.errorMessage(error, fallback)
            : fallback;
        const safe = frappe.utils.escape_html(String(message || fallback));
        $main.html(`<div class="frappe-card" style="padding:24px;text-align:center">${safe}</div>`);
        frappe.show_alert({ message, indicator: "red" }, 7);
    }

    if (
        !frontend
        || typeof frontend.requireAssets !== "function"
        || typeof frontend.ensureStylesheet !== "function"
    ) {
        showBootstrapError(new Error("Almdina frontend foundation is unavailable"));
        return;
    }

    const moduleLoad = frontend.requireAssets(MODULES);
    const styleLoad = frontend.ensureStylesheet(STYLESHEET, {
        id: "almdina-workforce-console-style",
    });

    Promise.all([moduleLoad, styleLoad])
        .then(() => {
            const controller = window.AlmdinaFactoryWorkforceController;
            if (!controller || typeof controller.mount !== "function") {
                throw new Error("Factory workforce controller did not initialize");
            }
            controller.mount(wrapper);
        })
        .catch(showBootstrapError);
};
