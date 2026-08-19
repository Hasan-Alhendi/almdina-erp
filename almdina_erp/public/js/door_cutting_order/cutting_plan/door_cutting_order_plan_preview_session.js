(() => {
    "use strict";

    if (window.AlmdinaPlanPreviewSession) return;

    const STATE_KEY = "__almdinaPlanPreviewSession";

    function emptyState() {
        return {
            status: "idle",
            previewId: null,
            payload: null,
            error: null,
        };
    }

    function stateFor(frm) {
        if (!frm) return emptyState();
        if (!frm[STATE_KEY]) frm[STATE_KEY] = emptyState();
        return frm[STATE_KEY];
    }

    function snapshot(frm) {
        const state = stateFor(frm);
        return Object.freeze({
            status: state.status,
            previewId: state.previewId,
            payload: state.payload ? JSON.parse(JSON.stringify(state.payload)) : null,
            error: state.error,
        });
    }

    function dispatch(frm) {
        // Preview is a separate transient state boundary. Do not trigger the
        // canonical Plan refresh hooks here: those would tear down the detached
        // settings editor on every keystroke/preview transition.
        window.dispatchEvent(new CustomEvent("almdina:plan-preview-updated", {
            detail: {
                orderName: frm && frm.doc ? frm.doc.name : null,
                preview: snapshot(frm),
            },
        }));
    }

    function reset(frm) {
        if (!frm) return;
        frm[STATE_KEY] = emptyState();
        dispatch(frm);
    }

    function invalidate(frm) {
        const state = stateFor(frm);
        if (state.status === "idle" || state.status === "stale") return false;
        state.status = "stale";
        state.previewId = null;
        state.payload = null;
        state.error = null;
        dispatch(frm);
        return true;
    }

    function isBusy(frm) {
        const status = stateFor(frm).status;
        return status === "previewing" || status === "saving";
    }

    function isReady(frm) {
        const state = stateFor(frm);
        return Boolean(
            state.status === "ready"
            && state.previewId
            && state.payload
            && state.payload.plan
        );
    }

    function isCommittable(frm) {
        const state = stateFor(frm);
        const validation = state.payload && state.payload.summary && state.payload.summary.validation;
        return Boolean(
            isReady(frm)
            && validation
            && String(validation.status || "") === "Valid"
            && !validation.needs_recalculation
        );
    }

    function previewPlan(frm) {
        return isReady(frm) ? stateFor(frm).payload.plan : null;
    }

    function previewRow(frm) {
        if (!isReady(frm)) return null;
        const payload = stateFor(frm).payload || {};
        const summary = payload.summary || {};
        return {
            name: `preview:${stateFor(frm).previewId}`,
            source_type: "System",
            snapshot_json: payload.plan || null,
            settings: { ...(summary.settings || {}) },
            engine: { ...(summary.engine || {}) },
            quality: { ...(summary.quality || {}) },
            totals: { ...(summary.totals || {}) },
            validation: { ...(summary.validation || {}) },
            is_preview: true,
        };
    }

    async function preview(frm, settings) {
        if (!frm || !frm.doc || !frm.doc.name || isBusy(frm)) return false;
        const api = window.AlmdinaPlanWorkspaceAPI;
        if (!api || typeof api.preview !== "function") {
            frappe.msgprint(__("تعذر تحميل خدمة معاينة خطة القص. أعد تحميل الصفحة."));
            return false;
        }

        const state = stateFor(frm);
        state.status = "previewing";
        state.previewId = null;
        state.payload = null;
        state.error = null;
        dispatch(frm);
        try {
            const payload = await api.preview(frm.doc.name, settings || {});
            if (!payload || !payload.preview_id || !payload.plan) {
                throw new Error("Invalid cutting-plan preview response");
            }
            state.status = "ready";
            state.previewId = payload.preview_id;
            state.payload = payload;
            state.error = null;
            dispatch(frm);
            return true;
        } catch (error) {
            state.status = "error";
            state.previewId = null;
            state.payload = null;
            state.error = String(error && (error.message || error) || __("تعذر إنشاء المعاينة."));
            dispatch(frm);
            throw error;
        }
    }

    async function commit(frm) {
        if (!frm || !frm.doc || !isCommittable(frm) || isBusy(frm)) return false;
        const api = window.AlmdinaPlanWorkspaceAPI;
        if (!api || typeof api.commitPreview !== "function") return false;

        const state = stateFor(frm);
        const previewId = state.previewId;
        state.status = "saving";
        state.error = null;
        dispatch(frm);
        try {
            const result = await api.commitPreview(frm.doc.name, previewId);
            frm[STATE_KEY] = emptyState();
            dispatch(frm);
            return result || true;
        } catch (error) {
            // The server consumes preview tokens even when a stale commit is
            // rejected. Mark it stale so Save cannot replay the same token.
            state.status = "stale";
            state.previewId = null;
            state.payload = null;
            state.error = String(error && (error.message || error) || __("تعذر حفظ المعاينة."));
            dispatch(frm);
            throw error;
        }
    }

    window.AlmdinaPlanPreviewSession = Object.freeze({
        snapshot,
        reset,
        invalidate,
        isBusy,
        isReady,
        isCommittable,
        previewPlan,
        previewRow,
        preview,
        commit,
    });
})();
