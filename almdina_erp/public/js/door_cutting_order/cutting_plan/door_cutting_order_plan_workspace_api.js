(() => {
    "use strict";

    if (window.AlmdinaPlanWorkspaceAPI) return;

    const READ_METHOD =
        "almdina_erp.almdina_erp.services.cutting_plan_workspace_query_service.get_plan_workspace_snapshot";
    const SAVE_SETTINGS_METHOD =
        "almdina_erp.almdina_erp.services.plan_settings_edit_service.save_plan_settings";
    const RECALCULATE_METHOD =
        "almdina_erp.almdina_erp.services.order_plan_permission_service.recalculate_order";
    const PREVIEW_METHOD =
        "almdina_erp.almdina_erp.services.cutting_plan_preview_service.preview_cutting_plan";
    const COMMIT_PREVIEW_METHOD =
        "almdina_erp.almdina_erp.services.cutting_plan_preview_service.commit_cutting_plan_preview";
    const SELECT_CANDIDATE_METHOD = "almdina_erp.almdina_erp.services.cutting_plan_preview_service.select_cutting_plan_candidate";
    const CONTINUE_SEARCH_METHOD = "almdina_erp.almdina_erp.services.cutting_plan_preview_service.continue_cutting_plan_search";
    const DISCARD_PREVIEW_METHOD = "almdina_erp.almdina_erp.services.cutting_plan_preview_service.discard_cutting_plan_preview";
    const APPROVE_METHOD =
        "almdina_erp.almdina_erp.services.drawing_approval_service.approve_production_dxf";
    const CANCEL_APPROVAL_METHOD =
        "almdina_erp.almdina_erp.services.drawing_approval_service.cancel_production_plan_approval";
    const SAVE_OFFCUT_ASSIGNMENTS_METHOD =
        "almdina_erp.almdina_erp.services.offcut_service.set_offcut_execution_owner";

    const FREEZE_SAVE_SETTINGS = "Saving cutting plan settings...";
    const FREEZE_RECALCULATE = "Recalculating the cutting plan...";
    const FREEZE_BOOTSTRAP = "Creating the first cutting plan...";
    const FREEZE_PREVIEW = "Previewing the plan with these settings...";
    const FREEZE_COMMIT = "Saving the selected cutting plan...";
    const FREEZE_APPROVE = "Approving the cutting plan...";
    const FREEZE_CANCEL_APPROVAL = "Cancelling the cutting plan approval...";
    const FREEZE_OFFCUT = "Saving the offcut classification...";

    function translateCopy(message) {
        const locale = window.AlmdinaLocale;
        if (locale && typeof locale.translate === "function") return locale.translate(message);
        if (typeof __ === "function") return __(message);
        return String(message == null ? "" : message);
    }

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
                freezeMessage: translateCopy(FREEZE_SAVE_SETTINGS),
            }
        );
    }

    function recalculate(orderName, settings) {
        return call(
            RECALCULATE_METHOD,
            settingsArgs(orderName, settings),
            {
                freeze: true,
                freezeMessage: translateCopy(FREEZE_RECALCULATE),
            }
        );
    }

    function bootstrapPlan(orderName, settings) {
        return call(
            RECALCULATE_METHOD,
            settingsArgs(orderName, settings),
            {
                freeze: true,
                freezeMessage: translateCopy(FREEZE_BOOTSTRAP),
            }
        );
    }

    function preview(orderName, settings) {
        return call(
            PREVIEW_METHOD,
            settingsArgs(orderName, settings),
            {
                freeze: true,
                freezeMessage: translateCopy(FREEZE_PREVIEW),
            }
        );
    }

    function commitPreview(orderName, previewId, candidateId) {
        return call(
            COMMIT_PREVIEW_METHOD,
            {
                order_name: orderName,
                preview_id: previewId,
                candidate_id: candidateId,
            },
            {
                freeze: true,
                freezeMessage: translateCopy(FREEZE_COMMIT),
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
                freezeMessage: translateCopy(FREEZE_APPROVE),
            }
        );
    }

    function cancelApproval(orderName) {
        return call(
            CANCEL_APPROVAL_METHOD,
            { order_name: orderName },
            {
                freeze: true,
                freezeMessage: translateCopy(FREEZE_CANCEL_APPROVAL),
            }
        );
    }

    function saveOffcutAssignments(planName, assignments) {
        return call(
            SAVE_OFFCUT_ASSIGNMENTS_METHOD,
            {
                plan_name: planName,
                assignments: JSON.stringify(assignments || []),
            },
            {
                freeze: true,
                freezeMessage: translateCopy(FREEZE_OFFCUT),
            }
        );
    }

    window.AlmdinaPlanWorkspaceAPI = Object.freeze({
        READ_METHOD,
        SAVE_SETTINGS_METHOD,
        RECALCULATE_METHOD,
        PREVIEW_METHOD,
        COMMIT_PREVIEW_METHOD,
        APPROVE_METHOD,
        CANCEL_APPROVAL_METHOD,
        SAVE_OFFCUT_ASSIGNMENTS_METHOD,
        load,
        saveSettings,
        recalculate,
        bootstrapPlan,
        preview,
        commitPreview,
        selectCandidate: (orderName, previewId, candidateId) => call(SELECT_CANDIDATE_METHOD, { order_name: orderName, preview_id: previewId, candidate_id: candidateId }),
        continueSearch: (orderName, previewId) => call(CONTINUE_SEARCH_METHOD, { order_name: orderName, preview_id: previewId }),
        discardPreview: (orderName, previewId) => call(DISCARD_PREVIEW_METHOD, { order_name: orderName, preview_id: previewId }),
        approve,
        cancelApproval,
        saveOffcutAssignments,
    });
})();
