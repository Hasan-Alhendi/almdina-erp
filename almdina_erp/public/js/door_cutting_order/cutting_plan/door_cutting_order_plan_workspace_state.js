(() => {
    "use strict";

    if (window.AlmdinaPlanWorkspaceState) return;

    const STORE_KEY = "__almdinaPlanWorkspaceStore";
    const LOAD_PROMISE_KEY = "__almdinaPlanWorkspaceLoadPromise";
    const LOADED_IDENTITY_KEY = "__almdinaPlanWorkspaceLoadedIdentity";

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

    function reset(frm) {
        const store = storeFor(frm);
        if (!store) return null;
        frm[LOADED_IDENTITY_KEY] = null;
        frm[LOAD_PROMISE_KEY] = null;
        const snapshot = store.reset(identity(frm));
        dispatch(frm, snapshot);
        return snapshot;
    }

    function invalidate(frm, reason = "dependency_changed") {
        const store = storeFor(frm);
        if (!store || typeof store.invalidate !== "function") return false;
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
        dispatch(frm, settled);
        return settled;
    }

    function rejectIdentityTransition(frm, store, expectedIdentity) {
        const liveIdentity = identity(frm);
        if (liveIdentity === expectedIdentity) return false;
        frm[LOADED_IDENTITY_KEY] = null;
        store.reset(liveIdentity);
        dispatch(frm, store.snapshot());
        return true;
    }

    function isFreshReady(frm, store, currentIdentity) {
        const current = store.snapshot();
        return Boolean(
            frm[LOADED_IDENTITY_KEY] === currentIdentity
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
            if (frm[LOAD_PROMISE_KEY] === promise) frm[LOAD_PROMISE_KEY] = null;
        });
        return { promise, resolveFlight, rejectFlight };
    }

    async function load(frm, options = {}) {
        if (!frm || !frm.doc || frm.doctype !== "Door Cutting Order") return null;
        const store = storeFor(frm);
        const api = window.AlmdinaPlanWorkspaceAPI;
        if (!store || !api || typeof api.load !== "function") return null;

        const currentIdentity = identity(frm);
        const orderName = String(frm.doc.name || "").trim();
        if (!orderName || (frm.is_new && frm.is_new()) || !canView(frm)) {
            return settleUnavailable(frm, store, currentIdentity);
        }

        if (!options.force && isFreshReady(frm, store, currentIdentity)) {
            return store.snapshot();
        }

        const pending = frm[LOAD_PROMISE_KEY];
        if (pending) {
            if (!options.force) return pending;

            // A forced lifecycle refresh must not race a still-current read. Wait
            // for that flight first; only start a follow-up when invalidation or an
            // error left the workspace non-fresh after the original request settled.
            try {
                await pending;
            } catch (error) {
                // The store owns the error state. Force below decides whether a
                // retry is still valid for the same live document identity.
            }
            if (identity(frm) !== currentIdentity) return store.snapshot();
            if (isFreshReady(frm, store, currentIdentity)) return store.snapshot();
            return load(frm, { force: true });
        }

        const { promise, resolveFlight, rejectFlight } = createFlight(frm);

        // Install the single-flight barrier before beginLoad()/dispatch(). Both
        // are observable synchronously, so listeners must see an owned in-flight
        // request before they can re-enter this loader.
        frm[LOAD_PROMISE_KEY] = promise;
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
                if (rejectIdentityTransition(frm, store, currentIdentity)) {
                    return store.snapshot();
                }
                const accepted = store.resolveLoad(currentIdentity, requestId, payload);
                if (!accepted) return store.snapshot();
                frm[LOADED_IDENTITY_KEY] = currentIdentity;
                const snapshot = store.snapshot();
                dispatch(frm, snapshot);
                return snapshot;
            })
            .catch((error) => {
                if (rejectIdentityTransition(frm, store, currentIdentity)) {
                    return store.snapshot();
                }
                store.rejectLoad(currentIdentity, requestId, error);
                const snapshot = store.snapshot();
                dispatch(frm, snapshot);
                throw error;
            })
            .then(resolveFlight, rejectFlight);

        return promise;
    }

    function snapshot(frm) {
        const store = storeFor(frm);
        return store ? store.snapshot() : null;
    }

    function activePlan(frm, preferredSource = "System") {
        const state = snapshot(frm);
        const data = state && state.data;
        const plans = data && data.plans;
        if (!plans) return null;
        if (preferredSource === "Uploaded DXF") {
            return plans.uploaded_draft || plans.approved || plans.system_draft || null;
        }
        return plans.system_draft || plans.approved || plans.uploaded_draft || null;
    }

    function schedule(frm, force = false) {
        if (!frm || frm.doctype !== "Door Cutting Order") return;
        const context = documentContext();
        const run = () => {
            load(frm, { force }).catch(() => {
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
        storeFor,
        reset,
        invalidate,
        load,
        snapshot,
        activePlan,
        schedule,
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