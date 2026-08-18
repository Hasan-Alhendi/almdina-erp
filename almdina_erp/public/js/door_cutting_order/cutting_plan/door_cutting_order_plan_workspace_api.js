(() => {
    "use strict";

    if (window.AlmdinaPlanWorkspaceAPI) return;

    const READ_METHOD =
        "almdina_erp.almdina_erp.services.cutting_plan_workspace_query_service.get_plan_workspace_snapshot";
    const SAVE_SETTINGS_METHOD =
        "almdina_erp.almdina_erp.services.plan_settings_edit_service.save_plan_settings";

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
                packing_mode: values.packing_mode,
                cutting_machine_type: values.cutting_machine_type,
                kerf_mm: values.kerf_mm,
                trim_margin_mm: values.trim_margin_mm,
                optimization_time_limit_sec: values.optimization_time_limit_sec,
            },
            {
                freeze: true,
                freezeMessage: __("جاري حفظ إعدادات خطة القص..."),
            }
        );
    }

    window.AlmdinaPlanWorkspaceAPI = Object.freeze({
        READ_METHOD,
        SAVE_SETTINGS_METHOD,
        load,
        saveSettings,
    });
})();
