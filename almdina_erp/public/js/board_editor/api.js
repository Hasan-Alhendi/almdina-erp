(() => {
    "use strict";

    const METHOD =
        "almdina_erp.almdina_erp.services.board_editor_query_service.get_board_editor_projection";
    const STATUS_METHOD =
        "almdina_erp.almdina_erp.services.cutting_plan_recalculation_job_service.get_system_plan_recalculation_status";
    const SAVE_METHOD =
        "almdina_erp.almdina_erp.services.board_editor_draft_service.save_board_editor_draft";
    const REVIEW_METHOD =
        "almdina_erp.almdina_erp.services.board_editor_draft_review_service.validate_board_editor_draft";
    const CREATE_PLAN_METHOD =
        "almdina_erp.almdina_erp.services.board_editor_plan_create_service.create_board_editor_plan_copy";
    const BEGIN_FROM_SOURCE_METHOD =
        "almdina_erp.almdina_erp.services.board_editor_draft_service.begin_board_editor_draft_from_current_source";

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

    function saveDraft(args) {
        const payload = args || {};
        return call(SAVE_METHOD, {
            order_name: String(payload.orderName || "").trim(),
            plan_name: String(payload.planName || "").trim(),
            expected_draft_version: Number(payload.expectedDraftVersion) || 0,
            source_content_revision: String(payload.sourceContentRevision || ""),
            layout: payload.layout || null,
        });
    }

    function reviewDraft(args) {
        const payload = args || {};
        return call(REVIEW_METHOD, {
            order_name: String(payload.orderName || "").trim(),
            plan_name: String(payload.planName || "").trim(),
        });
    }

    function createPlanCopy(args) {
        const payload = args || {};
        return call(CREATE_PLAN_METHOD, {
            order_name: String(payload.orderName || "").trim(),
            plan_name: String(payload.planName || "").trim(),
            expected_draft_version: Number(payload.expectedDraftVersion) || 0,
            source_content_revision: String(payload.sourceContentRevision || ""),
            source_input_fingerprint: String(payload.sourceInputFingerprint || ""),
            create_request_id: String(payload.createRequestId || ""),
            draft_name: String(payload.draftName || ""),
        });
    }

    function beginDraftFromCurrentSource(args) {
        const payload = args || {};
        return call(BEGIN_FROM_SOURCE_METHOD, {
            order_name: String(payload.orderName || "").trim(),
            plan_name: String(payload.planName || "").trim(),
            expected_draft_version: Number(payload.expectedDraftVersion) || 0,
            source_content_revision: String(payload.sourceContentRevision || ""),
        });
    }

    window.AlmdinaBoardEditor = window.AlmdinaBoardEditor || {};
    window.AlmdinaBoardEditor.Api = Object.freeze({
        load,
        recalculationStatus,
        saveDraft,
        reviewDraft,
        createPlanCopy,
        beginDraftFromCurrentSource,
        METHOD,
        STATUS_METHOD,
        SAVE_METHOD,
        REVIEW_METHOD,
        CREATE_PLAN_METHOD,
        BEGIN_FROM_SOURCE_METHOD,
    });
})();
