(() => {
    "use strict";

    if (window.AlmdinaPlanWorkspaceState) return;

    const STORE_KEY = "__almdinaPlanWorkspaceStore";
    const LOAD_PROMISE_KEY = "__almdinaPlanWorkspaceLoadPromise";
    const LOAD_OWNER_KEY = "__almdinaPlanWorkspaceLoadOwner";
    const LOADED_IDENTITY_KEY = "__almdinaPlanWorkspaceLoadedIdentity";
    const APPLY_RETURN_STATE_KEY = "__almdinaPlanApplyReturn";
    const APPLY_RETURN_STORAGE_PREFIX = "almdina.dco.planApplyReturn.";
    const APPLY_RETURN_MAX_AUTO_RETRIES = 3;

    function documentContext() {
        return window.AlmdinaDocumentContext || null;
    }

    function identity(frm) {
        const context = documentContext();
        if (context && typeof context.formIdentity === "function") {
            return context.formIdentity(frm);
        }
        if (!frm || !frm.doc) return "";
        return `${frm.doctype || frm.doc.doctype || ""}::${frm.doc.name || "__new__"}`;
    }

    function canView(frm) {
        const permissions = window.AlmdinaPermissions;
        if (!permissions || !frm) return false;
        if (typeof permissions.canDocument === "function") {
            return Boolean(permissions.canDocument(frm, "view_cutting_plan"));
        }
        return typeof permissions.can === "function"
            && Boolean(permissions.can("view_cutting_plan"));
    }

    function storeFor(frm) {
        if (!frm) return null;
        if (!frm[STORE_KEY]) {
            const factory = window.AlmdinaWorkspaceStore;
            if (!factory || typeof factory.create !== "function") return null;
            frm[STORE_KEY] = factory.create("plan");
        }
        return frm[STORE_KEY];
    }

    function dispatch(frm, snapshot) {
        window.dispatchEvent(new CustomEvent("almdina:plan-workspace-updated", {
            detail: {
                identity: identity(frm),
                orderName: frm && frm.doc ? frm.doc.name : null,
                snapshot,
            },
        }));
    }

    function ownedSnapshot(frm, store) {
        const state = store && store.snapshot();
        return state && state.identity === identity(frm)
            && (!state.data || payloadMatches(state.data, String(frm.doc?.name || "")))
            ? state : null;
    }

    function capture(frm) {
        const context = documentContext();
        return context?.capture?.(frm) || { identity: identity(frm) };
    }

    function owns(frm, token) {
        const context = documentContext();
        return context?.isSameDocument
            ? context.isSameDocument(frm, token)
            : identity(frm) === token.identity;
    }

    function payloadMatches(payload, orderName) {
        return Boolean(payload && String(payload.order_name || "") === orderName);
    }

    function translate(message, replacements) {
        const locale = window.AlmdinaLocale;
        if (locale && typeof locale.translate === "function") {
            return locale.translate(message, replacements);
        }
        if (typeof __ === "function") {
            return replacements === undefined ? __(message) : __(message, replacements);
        }
        let text = String(message == null ? "" : message);
        if (Array.isArray(replacements)) {
            replacements.forEach((value, index) => {
                text = text.split(`{${index}}`).join(String(value));
            });
        }
        return text;
    }

    function applyReturnStorageKey(orderName) {
        return `${APPLY_RETURN_STORAGE_PREFIX}${String(orderName || "").trim()}`;
    }

    function readStoredApplyReturn(orderName) {
        const key = String(orderName || "").trim();
        if (!key || typeof window === "undefined" || !window.sessionStorage) return null;
        try {
            const raw = window.sessionStorage.getItem(applyReturnStorageKey(key));
            if (!raw) return null;
            const parsed = JSON.parse(raw);
            const storedOrder = String(parsed && parsed.order_name || "").trim();
            const storedPlan = String(parsed && parsed.plan_name || "").trim();
            if (!storedOrder || storedOrder !== key || !storedPlan) return null;
            return {
                order_name: storedOrder,
                plan_name: storedPlan,
                prefer_tab: String(parsed.prefer_tab || "BoardEditor").trim() || "BoardEditor",
            };
        } catch (error) {
            return null;
        }
    }

    function clearStoredApplyReturn(orderName) {
        const key = String(orderName || "").trim();
        if (!key || typeof window === "undefined" || !window.sessionStorage) return;
        try {
            window.sessionStorage.removeItem(applyReturnStorageKey(key));
            // Legacy one-shot reload flag from earlier apply-return wiring.
            window.sessionStorage.removeItem(`almdina.dco.planWorkspaceReload.${key}`);
        } catch (error) {
            // Ignore storage failures; in-memory apply-return state still drives the visit.
        }
    }

    function clearApplyReturnState(frm) {
        if (!frm) return;
        frm[APPLY_RETURN_STATE_KEY] = null;
    }

    function applyReturnState(frm) {
        if (!frm) return null;
        const orderName = String(frm.doc && frm.doc.name || "").trim();
        const current = frm[APPLY_RETURN_STATE_KEY];
        if (current && String(current.order_name || "") === orderName) {
            return current;
        }
        if (current && String(current.order_name || "") !== orderName) {
            // Never carry an apply-return visit from order A onto order B.
            clearApplyReturnState(frm);
        }
        return null;
    }

    function ensureApplyReturnState(frm) {
        const orderName = String(frm && frm.doc && frm.doc.name || "").trim();
        if (!orderName) return null;
        const existing = applyReturnState(frm);
        if (existing && existing.plan_name) return existing;
        const stored = readStoredApplyReturn(orderName);
        if (!stored) return null;
        frm[APPLY_RETURN_STATE_KEY] = {
            order_name: stored.order_name,
            plan_name: stored.plan_name,
            prefer_tab: stored.prefer_tab || "BoardEditor",
            status: "pending",
            actual_plan_name: null,
            autoRetries: 0,
            message: null,
        };
        return frm[APPLY_RETURN_STATE_KEY];
    }

    function hasActiveApplyReturn(frm) {
        const state = applyReturnState(frm) || ensureApplyReturnState(frm);
        if (!state) return false;
        return ["pending", "waiting_row", "failed"].includes(String(state.status || ""));
    }

    function openEditedPlanTab(frm) {
        if (!frm) return;
        frm.__almdina_active_plan_tab = "BoardEditor";
    }

    function boardEditorDraftName(payload) {
        const row = payload && payload.plans && payload.plans.board_editor_draft;
        return String(row && row.name || "").trim();
    }

    function scheduleApplyReturnReadRetry(frm) {
        if (!frm || frm.doctype !== "Door Cutting Order") return;
        const context = documentContext();
        const run = () => {
            const pending = applyReturnState(frm);
            if (!pending || !["pending", "waiting_row", "failed"].includes(String(pending.status || ""))) {
                return;
            }
            load(frm, { force: true }).catch(() => {
                // Store owns the error state. Presenters own loading/error UI.
            });
        };
        if (context && typeof context.scheduleFrame === "function") {
            context.scheduleFrame(frm, "plan-workspace-apply-return-retry", run);
            return;
        }
        window.requestAnimationFrame(run);
    }

    function settleApplyReturn(frm, payload, { loadFailed = false } = {}) {
        const pending = applyReturnState(frm) || ensureApplyReturnState(frm);
        if (!pending) return null;
        const orderName = String(frm.doc && frm.doc.name || "").trim();
        if (pending.order_name !== orderName) {
            clearApplyReturnState(frm);
            return null;
        }

        if (loadFailed) {
            pending.status = "failed";
            pending.message = translate(
                "The edited cutting plan could not be refreshed after apply. Retry loading the plan."
            );
            frm[APPLY_RETURN_STATE_KEY] = pending;
            dispatch(frm, snapshot(frm));
            return pending;
        }

        const actualName = boardEditorDraftName(payload);
        if (!actualName) {
            // First apply can race the authorized BoardEditor row. Keep the return
            // context and retry the read only — never create another plan copy.
            pending.status = "waiting_row";
            pending.actual_plan_name = null;
            pending.message = translate("Waiting for the edited cutting plan to appear...");
            pending.autoRetries = Number(pending.autoRetries || 0);
            frm[APPLY_RETURN_STATE_KEY] = pending;
            if (pending.autoRetries < APPLY_RETURN_MAX_AUTO_RETRIES) {
                pending.autoRetries += 1;
                scheduleApplyReturnReadRetry(frm);
            } else {
                pending.status = "failed";
                pending.message = translate(
                    "The edited cutting plan could not be refreshed after apply. Retry loading the plan."
                );
            }
            dispatch(frm, snapshot(frm));
            return pending;
        }

        if (actualName === String(pending.plan_name || "")) {
            openEditedPlanTab(frm);
            clearStoredApplyReturn(orderName);
            clearApplyReturnState(frm);
            dispatch(frm, snapshot(frm));
            return null;
        }

        // A concurrent apply produced a newer authorized Edited plan than the one
        // this visit expected. Keep selection/permission rules, open Edited when
        // allowed, and distinguish the newer copy from the requested plan_name.
        pending.status = "newer";
        pending.actual_plan_name = actualName;
        pending.message = translate(
            "A newer edited cutting plan ({0}) is shown. It replaced the applied plan ({1}).",
            [actualName, pending.plan_name]
        );
        openEditedPlanTab(frm);
        clearStoredApplyReturn(orderName);
        frm[APPLY_RETURN_STATE_KEY] = pending;
        dispatch(frm, snapshot(frm));
        return pending;
    }

    function retryApplyReturnRead(frm) {
        const pending = applyReturnState(frm) || ensureApplyReturnState(frm);
        if (!pending) return Promise.resolve(null);
        pending.status = "pending";
        pending.message = null;
        pending.autoRetries = 0;
        frm[APPLY_RETURN_STATE_KEY] = pending;
        return load(frm, { force: true });
    }

    function reset(frm) {
        const store = storeFor(frm);
        if (!store) return null;
        frm[LOADED_IDENTITY_KEY] = null;
        frm[LOAD_PROMISE_KEY] = null;
        frm[LOAD_OWNER_KEY] = null;
        clearApplyReturnState(frm);
        const snapshot = store.reset(identity(frm));
        dispatch(frm, snapshot);
        return snapshot;
    }

    function invalidate(frm, reason = "dependency_changed") {
        const store = storeFor(frm);
        if (!ownedSnapshot(frm, store) || typeof store.invalidate !== "function") return false;
        const snapshot = store.invalidate(reason);
        dispatch(frm, snapshot);
        return snapshot;
    }

    function settleUnavailable(frm, store, currentIdentity) {
        const current = store.snapshot();
        if (
            frm[LOADED_IDENTITY_KEY] === currentIdentity
            && current.identity === currentIdentity
            && current.status === "idle"
        ) {
            return current;
        }

        const settled = store.reset(currentIdentity);
        frm[LOADED_IDENTITY_KEY] = currentIdentity;
        frm[LOAD_PROMISE_KEY] = null;
        frm[LOAD_OWNER_KEY] = null;
        dispatch(frm, settled);
        return settled;
    }

    function isFreshReady(frm, store, currentIdentity) {
        const current = ownedSnapshot(frm, store);
        return Boolean(
            current && frm[LOADED_IDENTITY_KEY] === currentIdentity
            && current.identity === currentIdentity
            && current.status === "ready"
            && current.freshness !== "stale"
        );
    }

    function createFlight(frm) {
        let resolveFlight;
        let rejectFlight;
        const flight = new Promise((resolve, reject) => {
            resolveFlight = resolve;
            rejectFlight = reject;
        });
        let promise = null;
        promise = flight.finally(() => {
            if (frm[LOAD_PROMISE_KEY] === promise) {
                frm[LOAD_PROMISE_KEY] = null;
                frm[LOAD_OWNER_KEY] = null;
            }
        });
        return { promise, resolveFlight, rejectFlight };
    }

    async function load(frm, options = {}) {
        if (!frm || !frm.doc || frm.doctype !== "Door Cutting Order") return null;
        const store = storeFor(frm);
        const api = window.AlmdinaPlanWorkspaceAPI;
        if (!store || !api || typeof api.load !== "function") return null;

        const currentIdentity = identity(frm);
        const requestToken = capture(frm);
        const orderName = String(frm.doc.name || "").trim();
        const applyReturn = ensureApplyReturnState(frm);
        const force = Boolean(options.force) || Boolean(applyReturn && hasActiveApplyReturn(frm));
        // A canonical read is deferred while the Plan workspace owns an edit
        // draft. resolveLoad() clears draft/editing, so loading here would lose
        // the operator's settings even when the read is only background sync.
        // Preserve apply-return context across that deferral so returning from the
        // board editor still forces a fresh read after settings edit exits.
        const current = store.snapshot();
        if (current.identity === currentIdentity && current.editing) {
            if (force && current.freshness !== "stale") {
                invalidate(
                    frm,
                    applyReturn ? "board_editor_apply_return_deferred" : "canonical_reload_deferred"
                );
            }
            return store.snapshot();
        }
        if (!orderName || (frm.is_new && frm.is_new()) || !canView(frm)) {
            return settleUnavailable(frm, store, currentIdentity);
        }

        if (!force && isFreshReady(frm, store, currentIdentity)) {
            return store.snapshot();
        }

        if (force && applyReturn && current.freshness !== "stale") {
            // Invalidate before transport so any GET that began before apply cannot
            // settle as current server truth after we return to the order.
            invalidate(frm, "board_editor_plan_applied");
        }

        const pending = frm[LOAD_PROMISE_KEY];
        if (pending && owns(frm, frm[LOAD_OWNER_KEY] || {})) {
            if (!force) return pending;

            // Concurrent activations (lifecycle + coordinator) coalesce into the
            // in-flight read. After it settles, start one follow-up only when the
            // apply-return visit or invalidation left the workspace non-fresh.
            try {
                await pending;
            } catch (error) {
                // The store owns the error state. Force below decides whether a
                // retry is still valid for the same live document identity.
            }
            if (!owns(frm, requestToken)) return snapshot(frm);
            if (isFreshReady(frm, store, currentIdentity) && !hasActiveApplyReturn(frm)) {
                return store.snapshot();
            }
            return load(frm, { force: true });
        }

        const { promise, resolveFlight, rejectFlight } = createFlight(frm);

        // Install the single-flight barrier before beginLoad()/dispatch(). Both
        // are observable synchronously, so listeners must see an owned in-flight
        // request before they can re-enter this loader.
        frm[LOAD_PROMISE_KEY] = promise;
        frm[LOAD_OWNER_KEY] = requestToken;
        const requestId = store.beginLoad(currentIdentity);
        dispatch(frm, store.snapshot());

        // Keep the established transport timing: callers that invoke load() see
        // the request start in the same tick. The ownership barrier above makes
        // this safe without deferring transport to another microtask.
        let transport;
        try {
            transport = api.load(orderName);
        } catch (error) {
            transport = Promise.reject(error);
        }

        Promise.resolve(transport)
            .then((payload) => {
                if (!owns(frm, requestToken)) return snapshot(frm);
                if (!payloadMatches(payload, orderName)) {
                    store.rejectLoad(currentIdentity, requestId, new Error("Plan response order mismatch"));
                    settleApplyReturn(frm, null, { loadFailed: true });
                    const invalid = snapshot(frm);
                    if (invalid) dispatch(frm, invalid);
                    return invalid;
                }
                const accepted = store.resolveLoad(currentIdentity, requestId, payload);
                if (!accepted) return snapshot(frm);
                frm[LOADED_IDENTITY_KEY] = currentIdentity;
                settleApplyReturn(frm, payload);
                const resultState = store.snapshot();
                dispatch(frm, resultState);
                return resultState;
            })
            .catch((error) => {
                if (!owns(frm, requestToken)) return snapshot(frm);
                store.rejectLoad(currentIdentity, requestId, error);
                settleApplyReturn(frm, null, { loadFailed: true });
                const resultState = store.snapshot();
                dispatch(frm, resultState);
                throw error;
            })
            .then(resolveFlight, rejectFlight);

        return promise;
    }

    function snapshot(frm) {
        const store = storeFor(frm);
        return ownedSnapshot(frm, store);
    }

    function isCurrentDraftRow(row) {
        return Boolean(row && String(row.status || "") === "Draft"
            && String(row.display_context || "current_draft") === "current_draft");
    }

    function activePlan(frm, preferredSource = "System") {
        const state = snapshot(frm);
        const data = state && state.data;
        const plans = data && data.plans;
        if (!plans) return null;
        const systemDraft = isCurrentDraftRow(plans.system_draft) ? plans.system_draft : null;
        const uploadedDraft = isCurrentDraftRow(plans.uploaded_draft) ? plans.uploaded_draft : null;
        const approved = plans.approved
            && String(plans.approved.status || "") === "Approved"
            && String(plans.approved.display_context || "current_approved") === "current_approved"
            ? plans.approved : null;
        if (preferredSource === "Uploaded DXF") {
            return uploadedDraft || approved || systemDraft || null;
        }
        return systemDraft || approved || uploadedDraft || null;
    }

    function planForTab(frm, tab) {
        const state = snapshot(frm);
        const data = state && state.data;
        const plans = data && data.plans;
        if (!plans) return null;
        if (tab === "Custom") return plans.uploaded_draft || null;
        if (tab === "Approved") return plans.approved || null;
        if (tab === "BoardEditor") {
            const row = plans.board_editor_draft || null;
            const pending = applyReturnState(frm);
            // While an apply-return visit still waits for the concrete plan_name,
            // do not expose a previous Edited plan as if it were the apply result.
            if (
                pending
                && ["pending", "waiting_row", "failed"].includes(String(pending.status || ""))
                && String(row && row.name || "").trim() !== String(pending.plan_name || "").trim()
            ) {
                return null;
            }
            return row;
        }
        return plans.system_draft || null;
    }

    function displayedPlanForTab(frm, tab) {
        if (tab === "System") {
            const preview = window.AlmdinaPlanPreviewSession;
            const row = preview && preview.displayedPreviewRow && preview.displayedPreviewRow(frm);
            if (row) return row;
        }
        return planForTab(frm, tab);
    }

    function displayedTab(frm) {
        const tabs = window.AlmdinaPlanTabsUX;
        if (tabs && typeof tabs.activeTab === "function") {
            return tabs.activeTab(frm);
        }
        return String(frm && frm.__almdina_active_plan_tab || "System");
    }

    function displayedPlan(frm) {
        return displayedPlanForTab(frm, displayedTab(frm));
    }

    function schedule(frm, force = false) {
        if (!frm || frm.doctype !== "Door Cutting Order") return;
        const context = documentContext();
        const run = () => {
            // apply-return context (order_name + plan_name) forces the read inside
            // load() through the same path WorkspaceSyncCoordinator uses.
            load(frm, { force: Boolean(force) }).catch(() => {
                // Store owns the error state. Presenters own only loading/error UI.
            });
        };
        if (context && typeof context.scheduleFrame === "function") {
            context.scheduleFrame(frm, "plan-workspace-state-load", run);
            return;
        }
        window.requestAnimationFrame(run);
    }

    const owner = Object.freeze({
        canView,
        isCurrentDraftRow,
        storeFor,
        reset,
        invalidate,
        load,
        snapshot,
        activePlan,
        planForTab,
        displayedPlanForTab,
        displayedPlan,
        schedule,
        applyReturnState,
        ensureApplyReturnState,
        hasActiveApplyReturn,
        retryApplyReturnRead,
        clearApplyReturnState,
    });
    window.AlmdinaPlanWorkspaceState = owner;

    const coordinator = window.AlmdinaWorkspaceSyncCoordinator;
    if (coordinator && typeof coordinator.register === "function") {
        coordinator.register("plan", {
            activationField: "results_tab",
            canLoad: canView,
            invalidate,
            load,
            snapshot,
        });
    }
})();
