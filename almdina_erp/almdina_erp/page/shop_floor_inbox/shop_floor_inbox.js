(() => {
    "use strict";

    const PAGE_ROUTE = "shop-floor-inbox";
    const FOUNDATION = "/assets/almdina_erp/js/frontend_foundation.js";
    const PAGE_LIFECYCLE = "/assets/almdina_erp/js/page_revisit_refresh.js";
    const FEATURE_ASSETS = Object.freeze([
        "/assets/almdina_erp/js/shop_floor_quick_actions.js",
        "/assets/almdina_erp/js/shop_floor_inbox/api.js",
        "/assets/almdina_erp/js/shop_floor_inbox/state.js",
        "/assets/almdina_erp/js/shop_floor_inbox/view_model.js",
        "/assets/almdina_erp/js/shop_floor_inbox/renderer.js",
        "/assets/almdina_erp/js/shop_floor_inbox/interactions.js",
        "/assets/almdina_erp/js/shop_floor_inbox/dialogs.js",
        "/assets/almdina_erp/js/shop_floor_inbox/controller.js",
    ]);
    const STYLESHEET = "/assets/almdina_erp/css/shop_floor_responsive.css";

    frappe.pages[PAGE_ROUTE].on_page_load = function (wrapper) {
        frappe.ui.make_app_page({
            parent: wrapper,
            title: __("صالة الإنتاج"),
            single_column: true,
        });
        const $main = $(wrapper).find(".layout-main-section");
        $main.html(`
            <div class="almdina-sf-shell">
                <div class="almdina-sf-state almdina-sf-loading" role="status" aria-live="polite">
                    <span class="almdina-sf-spinner" aria-hidden="true"></span>
                    <div><b>${__("جاري التحميل")}</b><span>${__("نجهّز صالة الإنتاج...")}</span></div>
                </div>
            </div>
        `);

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

        function showBootstrapError(error) {
            if (frappe.container && frappe.container.page && frappe.container.page !== wrapper) return null;
            const fallback = __("تعذر تحميل صالة الإنتاج.");
            const frontend = window.AlmdinaFrontend;
            const message = frontend && typeof frontend.errorMessage === "function"
                ? frontend.errorMessage(error, fallback)
                : String((error && error.message) || fallback);
            $main.html(`<div class="frappe-card" style="padding:24px;text-align:center">${frappe.utils.escape_html(message)}</div>`);
            frappe.show_alert({ message, indicator: "red" }, 7);
        }

        function bootstrap() {
            if (wrapper.__almdinaFrontendBootstrapPending) return wrapper.__almdinaFrontendBootstrapPending;
            const pending = ensureCore()
            .then(frontend => Promise.all([
                typeof frontend.requireAssets === "function"
                    ? frontend.requireAssets(FEATURE_ASSETS)
                    : Promise.resolve(frappe.require(FEATURE_ASSETS)),
                frontend.ensureStylesheet(STYLESHEET, { id: "almdina-shop-floor-responsive-css" }),
            ]))
            .then(() => {
                const controller = window.AlmdinaShopFloorInboxController;
                if (!controller || typeof controller.mount !== "function") {
                    throw new Error("Shop Floor Inbox controller did not initialize");
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
    frappe.pages[PAGE_ROUTE].on_page_show = wrapper => !wrapper.__almdinaFrontendBootstrapMounted && wrapper.__almdinaFrontendBootstrapRetry ? wrapper.__almdinaFrontendBootstrapRetry() : null;
})();
