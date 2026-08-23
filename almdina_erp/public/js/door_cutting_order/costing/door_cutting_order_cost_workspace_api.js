(() => {
    "use strict";

    if (window.AlmdinaCostWorkspaceAPI) return;

    const READ_METHOD =
        "almdina_erp.almdina_erp.services.cost_permission_service.get_order_cost_snapshot";
    const SAVE_SETTINGS_METHOD =
        "almdina_erp.almdina_erp.services.cost_permission_service.update_order_cost_settings";

    async function call(method, args, options = {}) {
        const response = await frappe.call({
            method,
            args,
            freeze: Boolean(options.freeze),
            freeze_message: options.freezeMessage || undefined,
        });
        return response && response.message !== undefined ? response.message : null;
    }

    function load(orderName) {
        return call(READ_METHOD, { order_name: orderName });
    }

    function saveSettings(orderName, settings) {
        const values = settings || {};
        return call(
            SAVE_SETTINGS_METHOD,
            {
                order_name: orderName,
                board_rate_usd: values.board_rate_usd,
                cutting_cost_per_board_usd: values.cutting_cost_per_board_usd,
            },
            {
                freeze: true,
                freezeMessage: __("جاري حفظ إعدادات التكلفة..."),
            }
        );
    }

    window.AlmdinaCostWorkspaceAPI = Object.freeze({
        READ_METHOD,
        SAVE_SETTINGS_METHOD,
        load,
        saveSettings,
    });
})();
