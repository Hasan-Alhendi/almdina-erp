(() => {
    "use strict";

    if (window.AlmdinaCostWorkspaceAPI) return;

    const READ_METHOD =
        "almdina_erp.almdina_erp.services.cost_permission_service.get_order_cost_snapshot";
    const SAVE_SETTINGS_METHOD =
        "almdina_erp.almdina_erp.services.cost_permission_service.update_order_cost_settings";

    async function call(method, args, options = {}) {
        const runtime = window.frappe || null;
        if (!runtime) throw new Error("Frappe RPC is unavailable");

        // Frappe v16 exposes xcall as the native Promise RPC boundary. Using it
        // first avoids the legacy jQuery Deferred callback path that can surface
        // opaque errors such as "s is not a function" in the Cost workspace.
        if (typeof runtime.xcall === "function" && !options.freeze) {
            const result = await runtime.xcall(method, args || {});
            return result && result.message !== undefined ? result.message : result;
        }

        if (typeof runtime.call !== "function") {
            throw new Error("Frappe RPC is unavailable");
        }

        const response = await runtime.call({
            method,
            args,
            freeze: Boolean(options.freeze),
            freeze_message: options.freezeMessage || undefined,
        });
        return response && response.message !== undefined ? response.message : response;
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
