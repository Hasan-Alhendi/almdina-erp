frappe.pages["factory-permissions"].on_page_load = function (wrapper) {
    "use strict";

    const FOUNDATION = "/assets/almdina_erp/js/frontend_foundation.js";
    const PAGE_LIFECYCLE = "/assets/almdina_erp/js/page_revisit_refresh.js";
    const MODULES = Object.freeze([
        "/assets/almdina_erp/js/almdina_ui.js",
        "/assets/almdina_erp/js/factory_permissions/api.js",
        "/assets/almdina_erp/js/factory_permissions/state.js",
        "/assets/almdina_erp/js/factory_permissions/view_model.js",
        "/assets/almdina_erp/js/factory_permissions/renderer.js",
        "/assets/almdina_erp/js/factory_permissions/interactions.js",
        "/assets/almdina_erp/js/factory_permissions/dialogs.js",
        "/assets/almdina_erp/js/factory_permissions/controller.js",
    ]);
    const STYLESHEET = "/assets/almdina_erp/css/factory_permissions.css?v=4";

    frappe.ui.make_app_page({
        parent: wrapper,
        title: __("إدارة صلاحيات المعمل"),
        single_column: true,
    });
    const $main = $(wrapper).find(".layout-main-section");
    const ui = window.AlmdinaUi;

    function paintState(kind, title, message) {
        const body = ui && typeof ui.state === "function"
            ? ui.state({ kind, title, message })
            : `<div class="alm-state alm-state--${kind}" role="${kind === "error" ? "alert" : "status"}"><strong class="alm-state__title">${frappe.utils.escape_html(title || "")}</strong>${message ? `<span class="alm-state__message">${frappe.utils.escape_html(String(message))}</span>` : ""}</div>`;
        $main.html(`<div class="almdina-ui">${body}</div>`);
    }

    paintState("loading", __("جاري تحميل مصفوفة الصلاحيات..."));

    function showBootstrapError(error) {
        const fallback = __("تعذر تحميل واجهة إدارة الصلاحيات.");
        const frontend = window.AlmdinaFrontend;
        const message = frontend && typeof frontend.errorMessage === "function"
            ? frontend.errorMessage(error, fallback)
            : String((error && error.message) || fallback);
        paintState("error", fallback, message);
        frappe.show_alert({ message, indicator: "red" }, 7);
    }

    function resolveCore() {
        const frontend = window.AlmdinaFrontend;
        const lifecycle = window.AlmdinaPageRevisit;
        if (!frontend || typeof frontend.ensureStylesheet !== "function") {
            throw new Error("Almdina frontend foundation did not initialize");
        }
        if (!lifecycle || typeof lifecycle.bindActivationLifecycle !== "function") {
            throw new Error("Almdina page lifecycle did not initialize");
        }
        return frontend;
    }

    function ensureCore() {
        const frontend = window.AlmdinaFrontend;
        const assets = [];
        if (!frontend || typeof frontend.ensureStylesheet !== "function") assets.push(FOUNDATION);
        if (!window.AlmdinaPageRevisit || typeof window.AlmdinaPageRevisit.bindActivationLifecycle !== "function") {
            assets.push(PAGE_LIFECYCLE);
        }
        if (!assets.length) return Promise.resolve(resolveCore());
        const pending = frontend && typeof frontend.requireAssets === "function"
            ? frontend.requireAssets(assets)
            : frappe.require(assets);
        return Promise.resolve(pending).then(resolveCore);
    }

    return ensureCore()
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
