(() => {
    "use strict";

    const PAGE_ROUTE = "shop-floor-inbox";
    const FOUNDATION = "/assets/almdina_erp/js/frontend_foundation.js";
    const PAGE_LIFECYCLE = "/assets/almdina_erp/js/page_revisit_refresh.js";
    const MODULES = Object.freeze([
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
        const page = frappe.ui.make_app_page({
            parent: wrapper,
            title: __("صالة الإنتاج"),
            single_column: true,
        });
        const $main = $(wrapper).find(".layout-main-section");
        $main.html(`
            <div class="almdina-sf-content">
                <div class="almdina-sf-shell" data-almdina-loading-owner="shop-floor-bootstrap">
                    <div class="almdina-sf-state almdina-sf-loading" role="status" aria-live="polite">
                        <span class="almdina-sf-spinner" aria-hidden="true"></span>
                        <div><b>${__("جاري التحميل")}</b><span>${__("جاري تجهيز صالة الإنتاج...")}</span></div>
                    </div>
                </div>
            </div>
        `);

        function renderBootstrapError(error) {
            const fallback = __("تعذر تحميل صالة الإنتاج.");
            const frontend = window.AlmdinaFrontend;
            const message = frontend && typeof frontend.errorMessage === "function"
                ? frontend.errorMessage(error, fallback)
                : String((error && error.message) || fallback);
            const safe = frappe.utils.escape_html(String(message || fallback));
            $main.html(`<div class="frappe-card" style="padding:24px;text-align:center">${safe}</div>`);
            frappe.show_alert({ message, indicator: "red" }, 7);
        }

        function showBootstrapError(error) {
            const namespace = ".almdinaShopFloorBootstrapError";
            const $wrapper = $(wrapper);
            if (!frappe.container || frappe.container.page !== wrapper) {
                $wrapper.off(namespace).on(`show${namespace}`, () => {
                    if (!frappe.container || frappe.container.page !== wrapper) return;
                    $wrapper.off(namespace);
                    renderBootstrapError(error);
                });
                return;
            }
            $wrapper.off(namespace);
            renderBootstrapError(error);
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
                const moduleLoad = typeof frontend.requireAssets === "function"
                    ? frontend.requireAssets(MODULES)
                    : Promise.resolve(frappe.require(MODULES));
                const styleLoad = frontend.ensureStylesheet(STYLESHEET, {
                    id: "almdina-shop-floor-responsive-css",
                });
                return Promise.all([moduleLoad, styleLoad]);
            })
            .then(() => {
                const controller = window.AlmdinaShopFloorInboxController;
                if (!controller || typeof controller.mount !== "function") {
                    throw new Error("Shop Floor Inbox controller did not initialize");
                }
                return controller.mount(wrapper, { page });
            })
            .catch(showBootstrapError);
    };
})();
