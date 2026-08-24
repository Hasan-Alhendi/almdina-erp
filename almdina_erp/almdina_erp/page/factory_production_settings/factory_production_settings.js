frappe.pages["factory-production-settings"].on_page_load = function (wrapper) {
    "use strict";

    const FOUNDATION = "/assets/almdina_erp/js/frontend_foundation.js";
    const PAGE_LIFECYCLE = "/assets/almdina_erp/js/page_revisit_refresh.js";
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

    frappe.ui.make_app_page({
        parent: wrapper,
        title: __("إعدادات المعمل"),
        single_column: true,
    });
    const $main = $(wrapper).find(".layout-main-section");
    $main.html(`
        <div class="aps-loading" role="status" aria-live="polite">
            <span class="aps-loading-dot" aria-hidden="true"></span>
            <div><strong>${__("جاري تحميل إعدادات المعمل")}</strong><span>${__("يتم تجهيز القيم والصلاحيات الحالية...")}</span></div>
        </div>
    `);

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
