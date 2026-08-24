frappe.pages["factory-workforce"].on_page_load = function (wrapper) {
    "use strict";

    const FOUNDATION = "/assets/almdina_erp/js/frontend_foundation.js";
    const PAGE_LIFECYCLE = "/assets/almdina_erp/js/page_revisit_refresh.js";
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

    frappe.ui.make_app_page({
        parent: wrapper,
        title: __("المستخدمون والقوى العاملة"),
        single_column: true,
    });
    const $main = $(wrapper).find(".layout-main-section");
    $main.html(`
        <div class="aw-loading" role="status" aria-live="polite">
            <span class="aw-loading-dot" aria-hidden="true"></span>
            <span>${__("جاري تحميل مستخدمي المعمل...")}</span>
        </div>
    `);

    function showBootstrapError(error) {
        if (frappe.container && frappe.container.page && frappe.container.page !== wrapper) return null;
        const fallback = __("تعذر تحميل واجهة المستخدمين والقوى العاملة.");
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

    function bootstrap() {
        if (wrapper.__almdinaFrontendBootstrapPending) return wrapper.__almdinaFrontendBootstrapPending;
        const pending = ensureCore()
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
            const mounted = controller.mount(wrapper);
            wrapper.__almdinaFrontendBootstrapMounted = true;
            return mounted;
        })
        .catch(showBootstrapError)
        .finally(() => { if (wrapper.__almdinaFrontendBootstrapPending === pending) wrapper.__almdinaFrontendBootstrapPending = null; });
        wrapper.__almdinaFrontendBootstrapPending = pending;
        return pending;
    }
    Object.assign(wrapper, { __almdinaFrontendBootstrapMounted: false, __almdinaFrontendBootstrapRetry: bootstrap });
    return bootstrap();
};
frappe.pages["factory-workforce"].on_page_show = wrapper => !wrapper.__almdinaFrontendBootstrapMounted && wrapper.__almdinaFrontendBootstrapRetry ? wrapper.__almdinaFrontendBootstrapRetry() : null;
