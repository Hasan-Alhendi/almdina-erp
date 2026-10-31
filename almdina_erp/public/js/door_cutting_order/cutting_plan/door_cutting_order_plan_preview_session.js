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

    function ownsVisit(frm, token) {
        const context = window.AlmdinaDocumentContext;
        return context?.isCurrent?.(frm, token)
            ?? (context?.isSameDocument?.(frm, token) !== false);
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

    function validPortfolio(payload) {
        if (!payload.candidates && !payload.preview_version) return true;
        const entries = payload.candidates;
        return Array.isArray(entries) && entries.length > 0 && entries.length <= 5
            && new Set(entries.map(c => c.candidate_id)).size === entries.length
            && entries.every(c => c.candidate_id && c.manufacturing_status === "Validated"
                && c.summary?.validation?.status === "Valid" && !c.summary.validation.needs_recalculation)
            && entries.some(c => c.candidate_id === payload.candidate_id)
            && payload.plan?.preview_candidate_id === payload.candidate_id;
    }

    function dropExpiry(state) {
        if (state.expiryTimer != null && window.clearTimeout) window.clearTimeout(state.expiryTimer);
        state.expiryTimer = null;
    }

    function armExpiry(frm, state) {
        dropExpiry(state);
        if (!state.expiresAt || !window.setTimeout) return;
        const token = state.previewId;
        state.expiryTimer = window.setTimeout(() => {
            if (frm[STATE_KEY] !== state || state.previewId !== token || !ownsVisit(frm, state.documentToken)) return;
            state.generation += 1;
            state.status = "stale";
            state.candidateBusy = false;
            state.previewId = null;
            state.payload = null;
            state.error = "The cutting plan preview expired. Create a new preview.";
            dispatch(frm);
        }, Math.max(0, state.expiresAt - Date.now()));
    }

    function exactCommitReceipt(result, state, orderName) {
        const payload = state.payload || {};
        return Boolean(result && typeof result === "object"
            && result.exact_preview_commit === true
            && result.committed_preview_id === state.previewId
            && (!payload.candidate_id || result.committed_candidate_id === payload.candidate_id)
            && (!payload.candidates?.find(c => c.candidate_id === payload.candidate_id)?.geometry_fingerprint
                || result.candidate_geometry_fingerprint === payload.candidates.find(c => c.candidate_id === payload.candidate_id).geometry_fingerprint)
            && result.name === orderName
            && (payload.is_first_system ? Boolean(result.cutting_plan) : result.cutting_plan === payload.source_plan_name)
            && Number.isInteger(Number(result.plan_revision))
            && Number(result.plan_revision) === Number(payload.source_plan_revision)
            && Number(result.plan_revision) > 0
            && result.plan_source_type === "System"
            && result.plan_status === "Draft"
            && SETTINGS.every(key => result[key] != null
                && (["kerf_mm", "trim_margin_mm", "optimization_time_limit_sec"].includes(key)
                    ? Number.isFinite(Number(result[key]))
                        && Number(result[key]) === Number(state.requestedSettings?.[key])
                    : String(result[key]) === String(state.requestedSettings?.[key]))));
    }

    function canonicalJson(value) {
        if (Array.isArray(value)) return value.map(canonicalJson);
        if (value && typeof value === "object") {
            return Object.fromEntries(Object.keys(value).sort().map(key => [key, canonicalJson(value[key])]));
        }
        return value;
    }

    async function reconcileCommittedPreview(api, state, orderName) {
        if (typeof api.load !== "function") return false;
        try {
            const data = await api.load(orderName);
            const row = data?.plans?.system_draft;
            const expected = state.payload;
            if (data?.order_name !== orderName || !row || !expected
                || (!expected.is_first_system && row.name !== expected.source_plan_name)
                || Number(row.revision) !== Number(expected.source_plan_revision)
                || !expected.source_plan_modified
                || !row.modified || String(row.modified) === String(expected.source_plan_modified)
                || row.source_type !== "System" || row.status !== "Draft"
                || row.validation?.status !== "Valid" || row.validation?.needs_recalculation) return false;
            const settings = row.settings || {};
            if (!SETTINGS.every(key => key in settings
                && (["kerf_mm", "trim_margin_mm", "optimization_time_limit_sec"].includes(key)
                    ? Number(settings[key]) === Number(state.requestedSettings[key])
                    : String(settings[key]) === String(state.requestedSettings[key])))) return false;
            const saved = typeof row.snapshot_json === "string"
                ? JSON.parse(row.snapshot_json) : row.snapshot_json;
            return Boolean(saved && JSON.stringify(canonicalJson(saved))
                === JSON.stringify(canonicalJson(expected.plan)));
        } catch (_error) {
            return false;
        }
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
            candidateBusy: false,
            expiresAt: null,
        };
    }

    function stateFor(frm) {
        if (!frm) return emptyState();
        if (!frm[STATE_KEY]) frm[STATE_KEY] = emptyState();
        const state = frm[STATE_KEY];
        const context = window.AlmdinaDocumentContext;
        if (state.identity && (context?.isSameDocument
            ? !context.isSameDocument(frm, state.documentToken || state.identity)
            : state.identity !== identity(frm))) {
            dropExpiry(state);
            frm[STATE_KEY] = { ...emptyState(), generation: state.generation + 1 };
        }
        return frm[STATE_KEY];
    }

    function snapshot(frm) {
        const state = stateFor(frm);
        return Object.freeze({
            status: state.status,
            previewId: state.previewId,
            payload: state.payload ? JSON.parse(JSON.stringify(state.payload)) : null,
            error: state.error,
            candidateBusy: state.candidateBusy,
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
        dropExpiry(previous);
        if (previous.previewId && window.AlmdinaPlanWorkspaceAPI?.discardPreview) {
            Promise.resolve(window.AlmdinaPlanWorkspaceAPI.discardPreview(frm.doc.name, previous.previewId)).catch(() => {});
        }
        frm[STATE_KEY] = { ...emptyState(), generation: previous.generation + 1 };
        dispatch(frm);
    }

    function invalidate(frm) {
        const state = stateFor(frm);
        if (state.status === "idle" || state.status === "stale" || state.status === "saving") return false;
        dropExpiry(state);
        state.generation += 1;
        state.candidateBusy = false;
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
        return status === "previewing" || status === "saving" || stateFor(frm).candidateBusy;
    }

    function isReady(frm) {
        const state = stateFor(frm);
        return Boolean(
            state.status === "ready"
            && state.previewId
            && (!state.expiresAt || Date.now() < state.expiresAt)
            && state.payload
            && state.payload.plan
            && state.identity === identity(frm)
            && ownsVisit(frm, state.documentToken)
        );
    }

    function isCommittable(frm) {
        const state = stateFor(frm);
        const validation = state.payload && state.payload.summary && state.payload.summary.validation;
        return Boolean(
            isReady(frm)
            && !state.candidateBusy
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
        if (state.identity !== identity(frm) || !ownsVisit(frm, state.documentToken)
            || !state.payload || !state.payload.plan) return null;
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

    function translate(message, replacements) {
        const locale = window.AlmdinaLocale;
        if (locale && typeof locale.translate === "function") {
            return locale.translate(message, replacements);
        }
        if (typeof __ === "function") {
            return replacements === undefined ? __(message) : __(message, replacements);
        }
        return String(message == null ? "" : message);
    }

    async function preview(frm, settings) {
        if (!frm || !frm.doc || !frm.doc.name || isBusy(frm)) return false;
        const api = window.AlmdinaPlanWorkspaceAPI;
        if (!api || typeof api.preview !== "function") {
            frappe.msgprint(translate("Could not load the cutting plan preview service. Reload the page."));
            return false;
        }

        const state = stateFor(frm);
        const requestIdentity = identity(frm);
        const orderName = frm.doc.name;
        const requested = settingsSnapshot({ ...(settings || {}), packing_mode: "smart" });
        const generation = ++state.generation;
        state.activeRequestGeneration = generation;
        state.requestedSettings = requested;
        state.identity = requestIdentity;
        state.documentToken = window.AlmdinaDocumentContext?.capture?.(frm) || requestIdentity;
        const current = () => frm[STATE_KEY] === state
            && state.generation === generation
            && state.activeRequestGeneration === generation
            && identity(frm) === requestIdentity
            && ownsVisit(frm, state.documentToken);
        state.status = "previewing";
        state.previewId = null;
        state.payload = null;
        state.error = null;
        dispatch(frm);
        try {
            const payload = await api.preview(orderName, { ...requested });
            if (!current()) return false;
            if (!payload || !payload.preview_id || !payload.plan
                || payload.order_name !== orderName
                || !payload.source_plan_name
                || !payload.source_plan_modified
                || !Number.isInteger(Number(payload.source_plan_revision))
                || Number(payload.source_plan_revision) < 1) {
                throw new Error("Invalid cutting-plan preview response");
            }
            if (!matchesSettings(payload, requested) || !validPortfolio(payload)) {
                throw new Error("Cutting-plan preview settings do not match the requested settings");
            }
            state.status = "ready";
            state.previewId = payload.preview_id;
            state.payload = payload;
            state.expiresAt = payload.expires_in_sec == null ? null : Date.now() + Number(payload.expires_in_sec) * 1000;
            armExpiry(frm, state);
            state.error = null;
            dispatch(frm);
            return true;
        } catch (error) {
            if (!current()) return false;
            state.status = "error";
            state.previewId = null;
            state.payload = null;
            state.error = String(
                (error && (error.message || error))
                || "Could not create the preview."
            );
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
        const commitGeneration = state.generation;
        const requestIdentity = identity(frm);
        const orderName = frm.doc.name;
        const requestToken = window.AlmdinaDocumentContext?.capture?.(frm) || requestIdentity;
        const current = () => frm[STATE_KEY] === state
            && state.generation === commitGeneration
            && state.previewId === previewId
            && state.status === "saving"
            && identity(frm) === requestIdentity
            && ownsVisit(frm, requestToken);
        state.status = "saving";
        state.error = null;
        dispatch(frm);
        async function finishUncertain(allowReconciliation = true) {
            const confirmed = allowReconciliation
                && await reconcileCommittedPreview(api, state, orderName);
            if (!current()) return false;
            if (confirmed) {
                frm[STATE_KEY] = { ...emptyState(), generation: state.generation + 1 };
                dispatch(frm);
                return { reconciled_commit: true };
            }
            state.status = "stale";
            state.previewId = null;
            state.payload = null;
            state.error = "The cutting plan save could not be confirmed. Check the saved plan, then create a new preview.";
            dispatch(frm);
            frappe.msgprint(translate(state.error));
            return false;
        }
        try {
            const result = await api.commitPreview(orderName, previewId, state.payload?.candidate_id);
            if (!current()) return false;
            if (!exactCommitReceipt(result, state, orderName)) {
                // A contradictory receipt is never promoted to a success by a
                // later read. Only absent or lost replies need reconciliation.
                return finishUncertain(result == null || result === false);
            }
            dropExpiry(state);
            frm[STATE_KEY] = { ...emptyState(), generation: state.generation + 1 };
            dispatch(frm);
            return result;
        } catch (error) {
            if (!current()) return false;
            const reconciled = await finishUncertain();
            if (reconciled) return reconciled;
            // A rejected or uncertain transaction consumes the token; the
            // operator must create a new preview instead of replaying it.
            state.error = String((error && (error.message || error)) || "Could not save the preview.");
            dispatch(frm);
            throw error;
        }
    }

    async function candidateRequest(frm, candidateId, continueSearch = false) {
        if (!isReady(frm) || isBusy(frm)) return false;
        const state = stateFor(frm), api = window.AlmdinaPlanWorkspaceAPI;
        if (!api) return false;
        if (continueSearch && !state.payload.can_continue) return false;
        if (!continueSearch && !state.payload.candidates?.some(c => c.candidate_id === candidateId)) return false;
        const token = state.previewId, generation = ++state.generation;
        state.candidateBusy = true;
        dispatch(frm);
        const current = () => frm[STATE_KEY] === state && state.generation === generation
            && state.previewId === token && state.identity === identity(frm) && ownsVisit(frm, state.documentToken);
        try {
            const payload = continueSearch ? await api.continueSearch(frm.doc.name, token)
                : await api.selectCandidate(frm.doc.name, token, candidateId);
            if (!current()) return false;
            if (!payload?.plan || payload.order_name !== frm.doc.name || !matchesSettings(payload, state.requestedSettings)
                || (!continueSearch && (payload.preview_id !== token || payload.candidate_id !== candidateId
                    || payload.plan.preview_candidate_id !== candidateId
                    || (state.payload.candidates.find(c => c.candidate_id === candidateId)?.geometry_fingerprint
                        && payload.geometry_fingerprint !== state.payload.candidates.find(c => c.candidate_id === candidateId).geometry_fingerprint)))) {
                throw new Error("Invalid cutting-plan candidate response");
            }
            if (continueSearch) {
                if (!payload.preview_id || !validPortfolio(payload)) throw new Error("Invalid search response");
                state.previewId = payload.preview_id;
                state.payload = payload;
                state.expiresAt = Date.now() + Number(payload.expires_in_sec || 0) * 1000;
                armExpiry(frm, state);
            } else {
                state.payload = { ...state.payload, plan: payload.plan, summary: payload.summary, candidate_id: candidateId };
            }
            return true;
        } catch (error) {
            if (current()) {
                state.status = "stale";
                state.previewId = null;
                state.payload = null;
                state.error = String(error?.message || error);
            }
            throw error;
        } finally {
            if (frm[STATE_KEY] === state && state.generation === generation) {
                state.candidateBusy = false;
                dispatch(frm);
            }
        }
    }

    window.AlmdinaPlanPreviewSession = Object.freeze({
        snapshot,
        selectCandidate: (frm, id) => candidateRequest(frm, id),
        continueSearch: frm => candidateRequest(frm, null, true),
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
