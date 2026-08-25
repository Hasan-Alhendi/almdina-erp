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
    const IDENTITY_ALIASES_FIELD = "__almdinaDocumentContextIdentityAliases";
    const PENDING_INSERT_FIELD = "__almdinaDocumentContextPendingInsert";

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

    function identityAliases(frm) {
        const aliases = frm && frm[IDENTITY_ALIASES_FIELD];
        return aliases instanceof Set ? aliases : null;
    }

    // Identity guard for *data*: the response still describes the document the
    // request was issued for. It deliberately ignores which form is on screen so
    // that a reply arriving during a route transition is still stored instead of
    // being dropped, which previously forced the user to refresh again.
    function isSameDocument(frm, token) {
        const identity = tokenIdentity(token);
        const currentIdentity = formIdentity(frm);
        if (!identity || !currentIdentity) return false;

        const generation = tokenGeneration(token);
        if (generation === null) return currentIdentity === identity;
        if (Number(frm._almdinaDocumentContextGeneration || 0) !== generation) {
            return false;
        }

        const aliases = identityAliases(frm);
        if (!aliases) return currentIdentity === identity;
        return aliases.has(identity) && aliases.has(currentIdentity);
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
        const measurementLifecycle = window.AlmdinaMeasurementLifecycle;
        if (measurementLifecycle && typeof measurementLifecycle.cancelAll === "function") {
            measurementLifecycle.cancelAll(frm);
        }
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
        frm.__almdina_actor_is_current_assignee = false;
        // Compatibility only: old modules may still read this name, but its
        // value mirrors assignment ownership, never role membership.
        frm.__almdina_actor_holds_stage_role = false;
        frm.__almdina_stage_operational_role = null;
        frm.__almdina_stage_context = null;
        frm.__almdina_stage_context_ready = false;
        frm.__almdina_stage_context_key = null;
        frm.__almdinaStageContextPromise = null;
        frm.__almdinaStageContextToken = null;
        frm.__almdinaStageContextRequestId = 0;
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
        frm.__almdinaSurfaceSettleRun = null;
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
        const assigned = stage.actor_is_current_assignee !== undefined
            ? Boolean(stage.actor_is_current_assignee)
            : Boolean(stage.actor_holds_operational_role);
        frm.__almdina_stage_context = stage;
        frm.__almdina_stage_type = stage.active_stage_type || null;
        frm.__almdina_actor_is_current_assignee = assigned;
        frm.__almdina_actor_holds_stage_role = assigned;
        frm.__almdina_stage_operational_role = stage.active_stage_operational_role || null;
        frm.__almdina_stage_context_ready = true;
        frm.__almdina_stage_context_key = String(frm.doc.current_production_stage || "");
    }

    function clearStageContext(frm) {
        const wasReady = frm.__almdina_stage_context_ready === true
            && frm.__almdina_stage_context_key === "";
        frm.__almdina_stage_context = null;
        frm.__almdina_stage_type = null;
        frm.__almdina_actor_is_current_assignee = false;
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

    function isCurrentStageAssignee(frm) {
        if (!frm || !frm.doc) return false;
        // Pre-production has no assignee yet; capabilities/lifecycle decide.
        // A route with no active stage has already left active production.
        if (!frm.doc.current_production_stage) {
            return !String(frm.doc.production_path || "").trim();
        }
        if (!frm.__almdina_stage_context_ready) return false;
        return Boolean(frm.__almdina_actor_is_current_assignee);
    }

    // Compatibility alias for older feature modules. It intentionally answers
    // assignment ownership now; operational roles are not authorization.
    function holdsStageOperationalRole(frm) {
        return isCurrentStageAssignee(frm);
    }

    function canMutateCurrentStage(frm) {
        if (!frm || !frm.doc) return false;
        if (isStageContextPending(frm)) return false;
        return isCurrentStageAssignee(frm);
    }

    // Tuning the cutting algorithm is a Plan capability. During an active route
    // it is additionally scoped to the current assignee, never to a role name.
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
    // throwaway copy and nothing is persisted. Capability checks remain server-side.
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
            return "جاري التحقق من إسناد المرحلة الحالية...";
        }
        if (isCurrentStageAssignee(frm)) return "";
        const stage = frm.__almdina_stage_context || {};
        if (stage.active_stage_assigned_to) {
            return "يمكنك عرض هذا الطلب فقط. المرحلة الحالية مسندة إلى مستخدم آخر.";
        }
        return "يمكنك عرض هذا الطلب فقط. أسند المرحلة الحالية إلى مستخدم قبل تنفيذ أي تعديل.";
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

    function notifySurfacesSettled(frm) {
        if (typeof window.dispatchEvent !== "function") return;
        window.dispatchEvent(new CustomEvent("almdina:surfaces-settled", {
            detail: { frm },
        }));
    }

    function settleSurfaces(frm, attempt) {
        if (!frm || !frm.doc || frm.doctype !== "Door Cutting Order") return false;
        const token = capture(frm);
        if (isCurrent(frm, token) === false) return false;

        const activeRun = frm.__almdinaSurfaceSettleRun;
        if (activeRun && isSameDocument(frm, activeRun.token)) {
            // A recovery may itself finish by asking the owner to settle again.
            // Never recurse into another recovery pass while the current one is
            // still in flight; that feedback loop previously generated thousands
            // of permission/stage requests for restricted roles.
            return false;
        }
        if (activeRun) frm.__almdinaSurfaceSettleRun = null;

        const step = Math.min(
            Math.max(Number(attempt) || 0, 0),
            SETTLE_DELAYS.length - 1
        );
        const pending = pendingSurfaces(frm);
        if (!pending.length) {
            notifySurfacesSettled(frm);
            return true;
        }

        const run = { token, step };
        frm.__almdinaSurfaceSettleRun = run;
        const recoveries = pending.map(({ name, probe }) => {
            try {
                return Promise.resolve(probe.recover(frm)).catch((error) => {
                    console.debug(`Almdina surface recovery failed: ${name}`, error);
                    return false;
                });
            } catch (error) {
                console.debug(`Almdina surface recovery failed: ${name}`, error);
                return Promise.resolve(false);
            }
        });

        Promise.all(recoveries)
            .then(() => {
                if (
                    frm.__almdinaSurfaceSettleRun !== run
                    || !isCurrent(frm, token)
                ) {
                    return;
                }
                const remaining = pendingSurfaces(frm);
                if (!remaining.length) {
                    notifySurfacesSettled(frm);
                    return;
                }
                if (step < SETTLE_DELAYS.length - 1) {
                    scheduleSettle(frm, step + 1);
                }
            })
            .catch((error) => {
                if (isCurrent(frm, token)) {
                    console.debug("Almdina surface settle pass failed", error);
                }
            })
            .finally(() => {
                if (frm.__almdinaSurfaceSettleRun === run) {
                    frm.__almdinaSurfaceSettleRun = null;
                }
            });

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

    function ensureStageContext(frm, options = {}) {
        if (!frm || !frm.doc || frm.is_new()) {
            return Promise.resolve(false);
        }

        const force = Boolean(options && options.force);
        const token = capture(frm);
        const stageName = String(frm.doc.current_production_stage || "").trim();
        if (!stageName) {
            if (clearStageContext(frm)) notifyStageContextReady(frm);
            return Promise.resolve(isSameDocument(frm, token));
        }

        const cacheKey = stageName;
        if (
            !force
            && frm.__almdina_stage_context_ready
            && frm.__almdina_stage_context_key === cacheKey
            && !frm.__almdinaStageContextPromise
        ) {
            return Promise.resolve(isSameDocument(frm, token));
        }

        if (
            !force
            && frm.__almdinaStageContextPromise
            && frm.__almdina_stage_context_key === cacheKey
            && isSameDocument(frm, frm.__almdinaStageContextToken)
        ) {
            return frm.__almdinaStageContextPromise;
        }

        const requestId = Number(frm.__almdinaStageContextRequestId || 0) + 1;
        frm.__almdinaStageContextRequestId = requestId;
        frm.__almdina_stage_context_ready = false;
        frm.__almdina_stage_context_key = cacheKey;
        frm.__almdinaStageContextToken = token;

        const promise = frappe
            .call({
                method: STAGE_CONTEXT_METHOD,
                args: { order_name: frm.doc.name },
            })
            .then((response) => {
                if (frm.__almdinaStageContextRequestId !== requestId) return false;
                if (!isSameDocument(frm, token)) return false;
                if (String(frm.doc.current_production_stage || "").trim() !== stageName) return false;
                applyStageContext(frm, response.message || {});
                notifyStageContextReady(frm);
                return true;
            })
            .catch((error) => {
                console.error("Failed to load production stage context", error);
                if (
                    frm.__almdinaStageContextRequestId === requestId
                    && isSameDocument(frm, token)
                ) {
                    frm.__almdina_stage_context = null;
                    frm.__almdina_actor_is_current_assignee = false;
                    frm.__almdina_actor_holds_stage_role = false;
                    frm.__almdina_stage_context_ready = true;
                    notifyStageContextReady(frm);
                }
                return false;
            })
            .finally(() => {
                if (frm.__almdinaStageContextRequestId !== requestId) return;
                if (frm.__almdinaStageContextPromise === promise) {
                    frm.__almdinaStageContextPromise = null;
                    frm.__almdinaStageContextToken = null;
                }
            });

        frm.__almdinaStageContextPromise = promise;
        return promise;
    }

    function refreshStageContext(frm) {
        return ensureStageContext(frm, { force: true });
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

        if (promotePendingInsert(frm, identity)) return false;

        frm._almdinaDocumentContextIdentity = identity;
        frm._almdinaDocumentContextGeneration = (
            Number(frm._almdinaDocumentContextGeneration || 0) + 1
        );
        frm[IDENTITY_ALIASES_FIELD] = new Set([identity]);
        frm[PENDING_INSERT_FIELD] = null;
        resetDocumentState(frm);
        clearDocumentHtml(frm);
        return true;
    }

    function beginSave(frm) {
        if (!frm || !frm.doc) return false;
        synchronize(frm);
        if (typeof frm.is_new !== "function" || !frm.is_new()) {
            frm[PENDING_INSERT_FIELD] = null;
            return false;
        }

        const token = capture(frm);
        if (!token) return false;
        frm[PENDING_INSERT_FIELD] = Object.freeze({
            token,
            doctype: String(frm.doc.doctype || frm.doctype || "").trim(),
            localName: String(frm.doc.name || "").trim(),
        });
        return true;
    }

    function mappedPermanentName(localName) {
        const names = frappe && frappe.model && frappe.model.new_names;
        return String((names && names[localName]) || "").trim();
    }

    function promotePendingInsert(frm, currentIdentity = formIdentity(frm)) {
        const pending = frm && frm[PENDING_INSERT_FIELD];
        if (!pending || !pending.token || !currentIdentity) return false;
        if (
            Number(frm._almdinaDocumentContextGeneration || 0)
            !== tokenGeneration(pending.token)
        ) {
            return false;
        }
        if (frm._almdinaDocumentContextIdentity !== pending.token.identity) return false;

        const doc = frm.doc || {};
        const localName = String(pending.localName || "").trim();
        const responseLocalName = String(doc.localname || "").trim();
        const permanentName = mappedPermanentName(localName)
            || (responseLocalName === localName ? String(doc.name || "").trim() : "");
        const promotedIdentity = permanentName
            ? `${pending.doctype}::${permanentName}`
            : "";
        if (!promotedIdentity || currentIdentity !== promotedIdentity) return false;

        const aliases = identityAliases(frm) || new Set([pending.token.identity]);
        aliases.add(pending.token.identity);
        aliases.add(promotedIdentity);
        frm[IDENTITY_ALIASES_FIELD] = aliases;
        frm._almdinaDocumentContextIdentity = promotedIdentity;
        return true;
    }

    function reconcileAfterSave(frm) {
        const pending = frm && frm[PENDING_INSERT_FIELD];
        if (!pending) {
            synchronize(frm);
            return false;
        }

        const promoted = promotePendingInsert(frm);
        frm[PENDING_INSERT_FIELD] = null;
        if (!promoted) synchronize(frm);
        return promoted;
    }

    window.AlmdinaDocumentContext = Object.freeze({
        HTML_FIELDS,
        formIdentity,
        capture,
        isCurrent,
        isSameDocument,
        synchronize,
        ensureStageContext,
        refreshStageContext,
        afterStageContext,
        isCurrentStageAssignee,
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
        before_save(frm) { beginSave(frm); },
        refresh(frm) {
            synchronize(frm);
            ensureStageContext(frm);
            scheduleSettle(frm, 0);
        },
        onload_post_render(frm) { scheduleSettle(frm, 0); },
        after_save(frm) {
            reconcileAfterSave(frm);
            scheduleSettle(frm, 0);
        },
    });

    if (typeof window.addEventListener === "function") {
        window.addEventListener("almdina:permissions-updated", () => {
            scheduleSettle(window.cur_frm, 0);
        });
    }
})();
