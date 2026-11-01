(() => {
    "use strict";

    const METHOD =
        "almdina_erp.almdina_erp.services.board_editor_query_service.get_board_editor_projection";
    const STATUS_METHOD =
        "almdina_erp.almdina_erp.services.cutting_plan_recalculation_job_service.get_system_plan_recalculation_status";

    function call(method, args) {
        return new Promise((resolve, reject) => {
            frappe.call({
                method,
                args,
                callback: (response) => resolve(response && response.message),
                error: (error) => reject(error),
            });
        });
    }

    function load(orderName, planName) {
        return call(METHOD, {
            order_name: String(orderName || "").trim(),
            plan_name: String(planName || "").trim(),
        });
    }

    function recalculationStatus(orderName) {
        return call(STATUS_METHOD, {
            order_name: String(orderName || "").trim(),
        });
    }

    window.AlmdinaBoardEditor = window.AlmdinaBoardEditor || {};
    window.AlmdinaBoardEditor.Api = Object.freeze({
        load,
        recalculationStatus,
        METHOD,
        STATUS_METHOD,
    });
})();
