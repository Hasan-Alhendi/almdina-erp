(() => {
    "use strict";

    const PAGE_ROUTE = "shop-floor-inbox";
    const FEATURE_ASSETS = [
        "/assets/almdina_erp/js/shop_floor_quick_actions.js",
        "/assets/almdina_erp/js/shop_floor_inbox/api.js",
        "/assets/almdina_erp/js/shop_floor_inbox/state.js",
        "/assets/almdina_erp/js/shop_floor_inbox/view_model.js",
        "/assets/almdina_erp/js/shop_floor_inbox/renderer.js",
        "/assets/almdina_erp/js/shop_floor_inbox/interactions.js",
        "/assets/almdina_erp/js/shop_floor_inbox/dialogs.js",
        "/assets/almdina_erp/js/shop_floor_inbox/controller.js",
        "/assets/almdina_erp/css/shop_floor_responsive.css",
    ];

    frappe.pages[PAGE_ROUTE].on_page_load = function (wrapper) {
        frappe.require(FEATURE_ASSETS, () => {
            window.AlmdinaShopFloorInboxController?.mount(wrapper);
        });
    };
})();
