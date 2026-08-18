(() => {
    "use strict";

    if (window.AlmdinaPlanWorkspaceAPI) return;

    const READ_METHOD =
        "almdina_erp.almdina_erp.services.cutting_plan_workspace_query_service.get_plan_workspace_snapshot";
    const SAVE_SETTINGS_METHOD =
        "almdina_erp.almdina_erp.services.plan_settings_edit_service.save_plan_settings";
    const RECALCULATE_METHOD =
        "almdina_erp.almdina_erp.services.order_plan_permission_service.recalculate_order";
    const APPROVE_METHOD =
        "almdina_erp.almdina_erp.services.drawing_approval_service.approve_production_dxf";

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

    function settingsArgs(orderName, settings) {
        const values = settings || {};
        return {
            order_name: orderName,
            packing_mode: values.packing_mode,
            cutting_machine_type: values.cutting_machine_type,
            kerf_mm: values.kerf_mm,
            trim_margin_mm: values.trim_margin_mm,
            optimization_time_limit_sec: values.optimization_time_limit_sec,
        };
    }

    function saveSettings(orderName, settings) {
        return call(
            SAVE_SETTINGS_METHOD,
            settingsArgs(orderName, settings),
            {
                freeze: true,
                freezeMessage: __("جاري حفظ إعدادات خطة القص..."),
            }
        );
    }

    function recalculate(orderName, settings) {
        return call(
            RECALCULATE_METHOD,
            settingsArgs(orderName, settings),
            {
                freeze: true,
                freezeMessage: __("جاري إعادة حساب خطة القص..."),
            }
        );
    }

    function approve(orderName, source) {
        return call(
            APPROVE_METHOD,
            {
                order_name: orderName,
                plan_source: source === "Custom" ? "Custom" : "System",
            },
            {
                freeze: true,
                freezeMessage: __("جاري اعتماد خطة القص..."),
            }
        );
    }

    window.AlmdinaPlanWorkspaceAPI = Object.freeze({
        READ_METHOD,
        SAVE_SETTINGS_METHOD,
        RECALCULATE_METHOD,
        APPROVE_METHOD,
        load,
        saveSettings,
        recalculate,
        approve,
    });
})();
