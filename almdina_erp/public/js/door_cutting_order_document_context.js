(() => {
    "use strict";

    if (window.AlmdinaDocumentContext) return;

    const HTML_FIELDS = Object.freeze([
        "operator_status_strip",
        "pieces_fast_entry",
        "order_cost_invoice_html",
        "plan_control_actions",
        "plan_controls_intro",
        "cutting_plan_html",
    ]);
    const TIMER_FIELDS = Object.freeze([
        "_dco_calc_timer",
        "__almdinaPlanSurfaceTimer",
        "__almdinaSurfaceSettleTimer",
    ]);
    const TIMER_MAP_FIELDS = Object.freeze([
        "_dco_fast_trigger_timers",
        "_dco_piece_type_trigger_timers",
    ]);
    // Mirrors the server lifecycle gate for pre-production plan recalculation.
    const ALGORITHM_TUNABLE_STATUSES = new Set(["Draft", "Pending Review", "Rejected"]);
    const OBSERVER_FIELDS = Object.freeze([
        "_dcoToolbarObserver",
        "_dcoMeasurementToolbarObserver",
        "__almdina_financial_observer",
        "__almdina_cost_actions_observer",
        "__almdina_invoice_button_observer",
        "__dcoSimplePlanControlsObserver",
        "__dcoMobileCardsObserver",
        "_almdina_secure_dxf_observer",
    ]);
    const EFFECT_STATE_FIELD = "__almdinaDocumentEffects";

    function formIdentity(frm) {
        const doc = frm && frm.doc;
        if (!doc) return "";
        const doctype = String(doc.doctype || frm.doctype || "").trim();
        const name = String(doc.name || "__new__").trim();
        return `${doctype}::${name}`;
    }

    function capture(frm) {
        const identity = formIdentity(frm);
        if (!identity) return null;
        return Object.freeze({
            identity,
            generation: Number(frm._almdinaDocumentContextGeneration || 0),
        });
    }

    function tokenIdentity(token) {
        if (typeof token === "string") return token;
        return token && typeof token === "object" ? String(token.identity || "") : "";
    }

    function tokenGeneration(token) {
        if (!token || typeof token !== "object") return null;
        const generation = Number(token.generation);
        return Number.isFinite(generation) ? generation : null;
    }

    // Identity guard for *data*: the response still describes the document the
    // request was issued for. It deliberately ignores which form is on screen so
    // that a reply arriving during a route transition is still stored instead of
    // being dropped, which previously forced the user to refresh again.
    function isSameDocument(frm, token) {
        const identity = tokenIdentity(token);
        if (!identity || formIdentity(frm) !== identity) return false;

        const generation = tokenGeneration(token);
        return (
            generation === null
            || Number(frm._almdinaDocumentContextGeneration || 0) === generation
        );
    }

    // Identity guard for *rendering*: additionally requires the form to be the
    // one the user is looking at.
    function isCurrent(frm, token) {
        if (!isSameDocument(frm, token)) return false;

        const activeForm = window.cur_frm;
        if (!activeForm) return true;
        return activeForm === frm;
    }

    function fieldWrapper(frm, fieldname) {
        const field = frm && frm.fields_dict && frm.fields_dict[fieldname];
        return field && (field.$wrapper || field.wrapper);
    }

    function clearWrapper(wrapper) {
        if (!wrapper) return;
        if (typeof wrapper.empty === "function") {
            wrapper.empty();
            return;
        }
        if (typeof wrapper.html === "function") {
            wrapper.html("");
            return;
        }

        const node = wrapper.nodeType ? wrapper : (wrapper[0] || null);
        if (!node) return;
        if (typeof node.replaceChildren === "function") {
            node.replaceChildren();
        } else {
            node.innerHTML = "";
        }
    }

    function clearDocumentHtml(frm) {
        HTML_FIELDS.forEach(fieldname => clearWrapper(fieldWrapper(frm, fieldname)));
    }

    function clearTimer(frm, fieldname) {
        const timer = frm[fieldname];
        if (!timer) return;
        window.clearTimeout(timer);
        frm[fieldname] = null;
    }

    function clearTimerMap(frm, fieldname) {
        const timers = frm[fieldname];
        if (!timers || typeof timers !== "object") return;
        Object.values(timers).forEach(timer => {
            if (timer) window.clearTimeout(timer);
        });
        frm[fieldname] = {};
    }

    function disconnectObserver(frm, fieldname) {
        const observer = frm[fieldname];
        if (observer && typeof observer.disconnect === "function") {
            observer.disconnect();
        }
        frm[fieldname] = null;
    }

    function effectState(frm) {
        if (!frm) return null;
        const current = frm[EFFECT_STATE_FIELD];
        if (
            current
            && current.timers instanceof Map
            && current.frames instanceof Map
            && current.observers instanceof Map
            && current.cleanups instanceof Map
        ) {
            return current;
        }
        const state = {
            timers: new Map(),
            frames: new Map(),
            observers: new Map(),
            cleanups: new Map(),
        };
        frm[EFFECT_STATE_FIELD] = state;
        return state;
    }

    function cancelEffect(frm, key) {
        const state = effectState(frm);
        const resolved = String(key || "").trim();
        if (!state || !resolved) return false;

        if (state.timers.has(resolved)) {
            window.clearTimeout(state.timers.get(resolved));
            state.timers.delete(resolved);
        }
        if (state.frames.has(resolved)) {
            const cancelFrame = window.cancelAnimationFrame || window.clearTimeout;
            cancelFrame.call(window, state.frames.get(resolved));
            state.frames.delete(resolved);
        }
        if (state.observers.has(resolved)) {
            const observer = state.observers.get(resolved);
            if (observer && typeof observer.disconnect === "function") observer.disconnect();
            state.observers.delete(resolved);
        }
        if (state.cleanups.has(resolved)) {
            const cleanup = state.cleanups.get(resolved);
            state.cleanups.delete(resolved);
            try {
                cleanup();
            } catch (error) {
                console.debug(`Almdina document cleanup failed: ${resolved}`, error);
            }
        }
        return true;
    }

    function schedule(frm, key, callback, delay = 0) {
        if (!frm || typeof callback !== "function") return null;
        const resolved = String(key || "").trim();
        if (!resolved) return null;
        cancelEffect(frm, resolved);
        const state = effectState(frm);
        const token = capture(frm);
        const timer = window.setTimeout(() => {
            if (state.timers.get(resolved) !== timer) return;
            state.timers.delete(resolved);
            if (!isCurrent(frm, token)) return;
            callback(frm, token);
        }, Math.max(0, Number(delay) || 0));
        state.timers.set(resolved, timer);
        return timer;
    }

    function scheduleFrame(frm, key, callback) {
        if (!frm || typeof callback !== "function") return null;
        const resolved = String(key || "").trim();
        if (!resolved) return null;
        cancelEffect(frm, resolved);
        const state = effectState(frm);
        const token = capture(frm);
        const requestFrame = window.requestAnimationFrame || window.setTimeout;
        const frame = requestFrame.call(window, () => {
            if (state.frames.get(resolved) !== frame) return;
            state.frames.delete(resolved);
            if (!isCurrent(frm, token)) return;
            callback(frm, token);
        });
        state.frames.set(resolved, frame);
        return frame;
    }

    function registerObserver(frm, key, observer) {
        if (!frm || !observer || typeof observer.disconnect !== "function") return false;
        const resolved = String(key || "").trim();
        if (!resolved) return false;
        cancelEffect(frm, resolved);
        effectState(frm).observers.set(resolved, observer);
        return true;
    }

    function registerCleanup(frm, key, cleanup) {
        if (!frm || typeof cleanup !== "function") return false;
        const resolved = String(key || "").trim();
        if (!resolved) return false;
        cancelEffect(frm, resolved);
        effectState(frm).cleanups.set(resolved, cleanup);
        return true;
    }

    function clearRegisteredEffects(frm) {
        const state = frm && frm[EFFECT_STATE_FIELD];
        if (!state) return;
        const keys = new Set([
            ...state.timers.keys(),
            ...state.frames.keys(),
            ...state.observers.keys(),
            ...state.cleanups.keys(),
        ]);
        keys.forEach(key => cancelEffect(frm, key));
        frm[EFFECT_STATE_FIELD] = null;
    }

    function cancelDocumentEffects(frm) {
        TIMER_FIELDS.forEach(fieldname => clearTimer(frm, fieldname));
        TIMER_MAP_FIELDS.forEach(fieldname => clearTimerMap(frm, fieldname));
        OBSERVER_FIELDS.forEach(fieldname => disconnectObserver(frm, fieldname));
        clearRegisteredEffects(frm);
    }

    function resetDocumentState(frm) {
        cancelDocumentEffects(frm);
        frm._dco_calc_version = Number(frm._dco_calc_version || 0) + 1;

        frm._dco_selected_piece_rows = new Set();
        frm._dco_edge_color_map = {};
        frm._dco_cost_render_deferred = false;
        frm._dco_piece_type_restore_token = null;
        frm._dco_plan_recalculation_running = false;
        frm._dcoTextBoardPlanBusy = false;
        frm.__almdina_active_plan_tab = null;
        frm.__almdina_algorithm_preview = null;
        frm.__almdina_approved_plan_snapshot = null;
        frm.__almdina_approved_plan_order = null;
        frm.__almdina_approved_plan_loading = null;
        frm.__almdina_approved_plan_context = null;
        frm.__almdina_stage_type = null;
        frm.__almdina_actor_holds_stage_role = false;
        frm.__almdina_stage_operational_role = null;
        frm.__almdina_stage_context = null;
        frm.__almdina_stage_context_ready = false;
        frm.__almdina_stage_context_key = null;
        frm.__almdinaStageContextPromise = null;
        frm.__almdinaStageContextToken = null;
        frm.__almdinaProductionRouteName = null;
        frm.__almdinaProductionRouteSteps = null;
        frm.__almdinaProductionActionsContext = null;
        frm.__almdinaProductionActionsKey = null;
        frm.__almdinaProductionActionsPromise = null;
        frm.__almdinaProductionRecoveryContext = null;
        frm.__almdinaProductionRecoveryPromise = null;
        frm.__almdinaPermissionRefreshContext = null;
        frm.__almdinaPermissionRefreshPromise = null;
        frm.__almdinaCostSnapshotContext = null;
        frm.__almdinaCostSnapshotPromise = null;
        frm.__almdina_cost_snapshot_order = null;
        frm.__almdina_invoice_cost_reconcile_identity = null;
        frm.__almdina_invoice_cost_reconcile_promise = null;
        frm.__almdina_pending_order_input_persistence = null;
        frm.__almdinaShopFloorHiddenState = null;
        frm._dcoToolbarObservedHead = null;
        frm._dcoMeasurementToolbarObservedRoot = null;
        frm._dco_fixed_tabs = null;
        frm._dco_tabs_placeholder = null;
        frm._dco_fixed_tabs_listener_installed = false;
        frm._dco_fixed_tabs_schedule = null;
        frm.__dcoSimplePlanControlsScheduled = false;

        delete frm._almdina_factory_defaults_loaded;
        delete frm._dco_added_buttons;
    }

    const STAGE_CONTEXT_METHOD =
        "almdina_erp.almdina_erp.services.shop_floor_query_service.get_current_stage_context";

    function applyStageContext(frm, message) {
        const stage = message || {};
        frm.__almdina_stage_context = stage;
        frm.__almdina_stage_type = stage.active_stage_type || null;
        frm.__almdina_actor_holds_stage_role = Boolean(stage.actor_holds_operational_role);
        frm.__almdina_stage_operational_role = stage.active_stage_operational_role || null;
        frm.__almdina_stage_context_ready = true;
        frm.__almdina_stage_context_key = String(frm.doc.current_production_stage || "");
    }

    function clearStageContext(frm) {
        const wasReady = frm.__almdina_stage_context_ready === true
            && frm.__almdina_stage_context_key === "";
        frm.__almdina_stage_context = null;
        frm.__almdina_stage_type = null;
        frm.__almdina_actor_holds_stage_role = false;
        frm.__almdina_stage_operational_role = null;
        frm.__almdina_stage_context_ready = true;
        frm.__almdina_stage_context_key = "";
        return !wasReady;
    }

    function isStageContextPending(frm) {
        return Boolean(
            frm
            && frm.doc
            && frm.doc.current_production_stage
            && !frm.__almdina_stage_context_ready
        );
    }

    function holdsStageOperationalRole(frm) {
        if (!frm || !frm.doc) return false;
        // Pre-production (no route yet): capability matrix alone decides.
        // Once a production path exists, an empty stage means the order left the
        // route (ready / delivered) and stage-scoped mutations must stay closed.
        if (!frm.doc.current_production_stage) {
            return !String(frm.doc.production_path || "").trim();
        }
        if (!frm.__almdina_stage_context_ready) return false;
        return Boolean(frm.__almdina_actor_holds_stage_role);
    }

    function canMutateCurrentStage(frm) {
        if (!frm || !frm.doc) return false;
        if (isStageContextPending(frm)) return false;
        return holdsStageOperationalRole(frm);
    }

    // Tuning the cutting algorithm is a plan-side surface governed by its own
    // capability. It never rides on the order edit session, so a role that only
    // carries «تعديل خوارزمية القص» can still change it and read the result.
    function canTuneCuttingAlgorithm(frm) {
        if (!frm || !frm.doc || frm.is_new()) return false;
        if (Number(frm.doc.docstatus || 0) !== 0) return false;
        if (frm.doc.approved_plan) return false;
        if (String(frm.doc.revision_state || "Current") === "Superseded") return false;
        if (!canMutateCurrentStage(frm)) return false;
        if (frm.doc.current_production_stage) return true;
        return ALGORITHM_TUNABLE_STATUSES.has(frm.doc.status || "Draft");
    }

    // Comparing algorithms is an inspection, not an edit: the engine runs on a
    // throwaway copy and nothing is persisted. It therefore stays open at every
    // stage and even on an approved plan, for anyone holding the capability.
    function canPreviewCuttingAlgorithm(frm) {
        return Boolean(frm && frm.doc && !frm.is_new());
    }

    function stageMutationBlockReason(frm) {
        if (!frm || !frm.doc) return "";
        if (!frm.doc.current_production_stage) {
            if (String(frm.doc.production_path || "").trim()) {
                return "يمكنك عرض هذا الطلب فقط. الطلب غادر مراحل الإنتاج النشطة.";
            }
            return "";
        }
        if (isStageContextPending(frm)) {
            return "جاري التحقق من صلاحية المرحلة الحالية...";
        }
        if (holdsStageOperationalRole(frm)) return "";
        const role = frm.__almdina_stage_operational_role;
        const stage = frm.__almdina_stage_type;
        if (role && stage) {
            return `يمكنك عرض هذا الطلب فقط. المرحلة الحالية «${stage}» مخصّصة للدور التشغيلي «${role}»، وليست ضمن أدوارك.`;
        }
        return "يمكنك عرض هذا الطلب فقط. مرحلته الحالية ليست ضمن أدوارك التشغيلية.";
    }

    // A surface is any region that a lazily loaded module owns. Rendering runs
    // after asynchronous prerequisites (permission context, stage context,
    // deferred module assets), so a single pass can legitimately produce
    // nothing. Each owner registers a readiness probe plus a recovery action and
    // the settle loop keeps retrying until every surface reports ready, which
    // removes the need for the user to refresh the page again.
    const SETTLE_DELAYS = Object.freeze([250, 700, 1500, 3000]);
    const surfaces = new Map();

    function registerSurface(name, probe) {
        const key = String(name || "").trim();
        if (
            !key
            || !probe
            || typeof probe.isReady !== "function"
            || typeof probe.recover !== "function"
        ) {
            return false;
        }
        surfaces.set(key, probe);
        return true;
    }

    function pendingSurfaces(frm) {
        const pending = [];
        surfaces.forEach((probe, name) => {
            let ready = false;
            try {
                ready = probe.isReady(frm) !== false;
            } catch (error) {
                console.debug(`Almdina surface probe failed: ${name}`, error);
            }
            if (!ready) pending.push({ name, probe });
        });
        return pending;
    }

    function settleSurfaces(frm, attempt) {
        if (!frm || !frm.doc || frm.doctype !== "Door Cutting Order") return false;
        if (!isCurrent(frm, capture(frm))) return false;

        const pending = pendingSurfaces(frm);
        if (!pending.length) return true;

        pending.forEach(({ name, probe }) => {
            try {
                Promise.resolve(probe.recover(frm)).catch((error) => {
                    console.debug(`Almdina surface recovery failed: ${name}`, error);
                });
            } catch (error) {
                console.debug(`Almdina surface recovery failed: ${name}`, error);
            }
        });

        if (attempt < SETTLE_DELAYS.length - 1) scheduleSettle(frm, attempt + 1);
        return false;
    }

    function scheduleSettle(frm, attempt = 0) {
        if (!frm || !frm.doc || frm.doctype !== "Door Cutting Order") return;
        if (!surfaces.size) return;
        if (frm.__almdinaSurfaceSettleTimer) {
            window.clearTimeout(frm.__almdinaSurfaceSettleTimer);
        }
        const step = Math.min(Math.max(Number(attempt) || 0, 0), SETTLE_DELAYS.length - 1);
        frm.__almdinaSurfaceSettleTimer = window.setTimeout(() => {
            frm.__almdinaSurfaceSettleTimer = null;
            settleSurfaces(frm, step);
        }, SETTLE_DELAYS[step]);
    }

    function notifyStageContextReady(frm) {
        scheduleSettle(frm, 0);
        if (typeof window.dispatchEvent !== "function") return;
        window.dispatchEvent(new CustomEvent("almdina:stage-context-ready", {
            detail: { frm },
        }));
    }

    function ensureStageContext(frm) {
        if (!frm || !frm.doc || frm.is_new()) {
            return Promise.resolve(false);
        }

        const token = capture(frm);
        const stageName = String(frm.doc.current_production_stage || "").trim();
        if (!stageName) {
            if (clearStageContext(frm)) notifyStageContextReady(frm);
            return Promise.resolve(isSameDocument(frm, token));
        }

        const cacheKey = stageName;
        if (
            frm.__almdina_stage_context_ready
            && frm.__almdina_stage_context_key === cacheKey
            && !frm.__almdinaStageContextPromise
        ) {
            return Promise.resolve(isSameDocument(frm, token));
        }

        if (
            frm.__almdinaStageContextPromise
            && frm.__almdina_stage_context_key === cacheKey
            && isSameDocument(frm, frm.__almdinaStageContextToken)
        ) {
            return frm.__almdinaStageContextPromise;
        }

        frm.__almdina_stage_context_ready = false;
        frm.__almdina_stage_context_key = cacheKey;
        frm.__almdinaStageContextToken = token;
        frm.__almdinaStageContextPromise = frappe
            .call({
                method: STAGE_CONTEXT_METHOD,
                args: { order_name: frm.doc.name },
            })
            .then((response) => {
                if (!isSameDocument(frm, token)) return false;
                if (frm.doc.current_production_stage !== stageName) return false;
                applyStageContext(frm, response.message || {});
                notifyStageContextReady(frm);
                return true;
            })
            .catch((error) => {
                console.error("Failed to load production stage context", error);
                if (isSameDocument(frm, token)) {
                    frm.__almdina_stage_context = null;
                    frm.__almdina_actor_holds_stage_role = false;
                    frm.__almdina_stage_context_ready = true;
                    notifyStageContextReady(frm);
                }
                return false;
            })
            .finally(() => {
                if (frm.__almdinaStageContextToken === token) {
                    frm.__almdinaStageContextPromise = null;
                    frm.__almdinaStageContextToken = null;
                }
            });

        return frm.__almdinaStageContextPromise;
    }

    function afterStageContext(frm, callback) {
        if (typeof callback !== "function") {
            return ensureStageContext(frm);
        }
        return ensureStageContext(frm).then((ready) => {
            const token = capture(frm);
            if (!ready || !isCurrent(frm, token)) return false;
            callback(frm);
            return true;
        });
    }

    function synchronize(frm) {
        const identity = formIdentity(frm);
        if (!identity || frm._almdinaDocumentContextIdentity === identity) {
            return false;
        }

        frm._almdinaDocumentContextIdentity = identity;
        frm._almdinaDocumentContextGeneration = (
            Number(frm._almdinaDocumentContextGeneration || 0) + 1
        );
        resetDocumentState(frm);
        clearDocumentHtml(frm);
        return true;
    }

    window.AlmdinaDocumentContext = Object.freeze({
        HTML_FIELDS,
        formIdentity,
        capture,
        isCurrent,
        isSameDocument,
        synchronize,
        ensureStageContext,
        afterStageContext,
        holdsStageOperationalRole,
        canMutateCurrentStage,
        canTuneCuttingAlgorithm,
        canPreviewCuttingAlgorithm,
        isStageContextPending,
        stageMutationBlockReason,
        registerSurface,
        cancelEffect,
        schedule,
        scheduleFrame,
        registerObserver,
        registerCleanup,
        pendingSurfaces,
        scheduleSettle,
        settleSurfaces,
    });

    frappe.ui.form.on("Door Cutting Order", {
        before_load(frm) { synchronize(frm); },
        onload(frm) { synchronize(frm); },
        refresh(frm) {
            synchronize(frm);
            ensureStageContext(frm);
            scheduleSettle(frm, 0);
        },
        onload_post_render(frm) { scheduleSettle(frm, 0); },
        after_save(frm) { scheduleSettle(frm, 0); },
    });

    if (typeof window.addEventListener === "function") {
        window.addEventListener("almdina:permissions-updated", () => {
            scheduleSettle(window.cur_frm, 0);
        });
    }
})();
