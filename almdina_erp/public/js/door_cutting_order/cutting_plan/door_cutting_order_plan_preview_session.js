(() => {
    "use strict";

    if (window.AlmdinaPlanPreviewSession) return;

    const STATE_KEY = "__almdinaPlanPreviewSession";
    const SETTINGS = ["packing_mode", "cutting_machine_type", "kerf_mm", "trim_margin_mm", "optimization_time_limit_sec"];

    function identity(frm) {
        const context = window.AlmdinaDocumentContext;
        return context && typeof context.formIdentity === "function"
            ? context.formIdentity(frm)
            : `${frm.doctype || frm.doc.doctype || ""}::${frm.doc.name || ""}`;
    }

    function settingsSnapshot(settings) {
        return Object.freeze(Object.fromEntries(SETTINGS.map(key => [key, settings && settings[key]])));
    }

    function matchesSettings(payload, requested) {
        const actual = payload && payload.summary && payload.summary.settings;
        return Boolean(actual && SETTINGS.every(key =>
            actual[key] !== undefined && requested[key] !== undefined
            && (["kerf_mm", "trim_margin_mm", "optimization_time_limit_sec"].includes(key)
                ? Number(actual[key]) === Number(requested[key])
                : String(actual[key]) === String(requested[key]))
        ));
    }

    function emptyState() {
        return {
            status: "idle",
            previewId: null,
            payload: null,
            error: null,
            generation: 0,
            activeRequestGeneration: null,
            requestedSettings: null,
            identity: null,
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
            requestedSettings: state.requestedSettings ? { ...state.requestedSettings } : null,
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
        const previous = stateFor(frm);
        frm[STATE_KEY] = { ...emptyState(), generation: previous.generation + 1 };
        dispatch(frm);
    }

    function invalidate(frm) {
        const state = stateFor(frm);
        if (state.status === "idle" || state.status === "stale") return false;
        state.generation += 1;
        state.activeRequestGeneration = null;
        state.requestedSettings = null;
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
            && state.identity === identity(frm)
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

    function displayedPreviewRow(frm) {
        const state = stateFor(frm);
        if (state.status !== "saving" && !isReady(frm)) return null;
        if (state.identity !== identity(frm) || !state.payload || !state.payload.plan) return null;
        return previewRowData(state);
    }

    function previewRowData(state) {
        const payload = state.payload || {};
        const summary = payload.summary || {};
        return {
            name: `preview:${state.previewId}`,
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

    function previewRow(frm) {
        if (!isReady(frm)) return null;
        return previewRowData(stateFor(frm));
    }

    async function preview(frm, settings) {
        if (!frm || !frm.doc || !frm.doc.name || isBusy(frm)) return false;
        const api = window.AlmdinaPlanWorkspaceAPI;
        if (!api || typeof api.preview !== "function") {
            frappe.msgprint(__("تعذر تحميل خدمة معاينة خطة القص. أعد تحميل الصفحة."));
            return false;
        }

        const state = stateFor(frm);
        const requestIdentity = identity(frm);
        const requested = settingsSnapshot(settings || {});
        const generation = ++state.generation;
        state.activeRequestGeneration = generation;
        state.requestedSettings = requested;
        state.identity = requestIdentity;
        const current = () => frm[STATE_KEY] === state
            && state.generation === generation
            && state.activeRequestGeneration === generation
            && identity(frm) === requestIdentity;
        state.status = "previewing";
        state.previewId = null;
        state.payload = null;
        state.error = null;
        dispatch(frm);
        try {
            const payload = await api.preview(frm.doc.name, { ...requested });
            if (!current()) return false;
            if (!payload || !payload.preview_id || !payload.plan) {
                throw new Error("Invalid cutting-plan preview response");
            }
            if (!matchesSettings(payload, requested)) {
                throw new Error("Cutting-plan preview settings do not match the requested settings");
            }
            state.status = "ready";
            state.previewId = payload.preview_id;
            state.payload = payload;
            state.error = null;
            dispatch(frm);
            return true;
        } catch (error) {
            if (!current()) return false;
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
        const requestIdentity = identity(frm);
        state.status = "saving";
        state.error = null;
        dispatch(frm);
        try {
            const result = await api.commitPreview(frm.doc.name, previewId);
            if (frm[STATE_KEY] !== state || identity(frm) !== requestIdentity) return false;
            frm[STATE_KEY] = { ...emptyState(), generation: state.generation + 1 };
            dispatch(frm);
            return result || true;
        } catch (error) {
            if (frm[STATE_KEY] !== state || identity(frm) !== requestIdentity) return false;
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
        displayedPreviewRow,
        preview,
        commit,
    });
})();
