(() => {
    "use strict";

    if (window.AlmdinaCostWorkspaceState) return;

    const STORE_KEY = "__almdinaCostWorkspaceStore";
    const LOAD_PROMISE_KEY = "__almdinaCostWorkspaceLoadPromise";
    const LOAD_OWNER_KEY = "__almdinaCostWorkspaceLoadOwner";
    const LOADED_IDENTITY_KEY = "__almdinaCostWorkspaceLoadedIdentity";
    const RECOVER_KEY = "__almdinaCostWorkspaceLoadRecoveries";

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
            return Boolean(permissions.canDocument(frm, "view_costs"));
        }
        return typeof permissions.can === "function"
            && Boolean(permissions.can("view_costs"));
    }

    function storeFor(frm) {
        if (!frm) return null;
        if (!frm[STORE_KEY]) {
            const factory = window.AlmdinaWorkspaceStore;
            if (!factory || typeof factory.create !== "function") return null;
            frm[STORE_KEY] = factory.create("cost");
        }
        return frm[STORE_KEY];
    }

    function dispatch(frm, snapshot) {
        window.dispatchEvent(new CustomEvent("almdina:cost-workspace-updated", {
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

    function reset(frm) {
        const store = storeFor(frm);
        if (!store) return null;
        frm[LOADED_IDENTITY_KEY] = null;
        frm[LOAD_PROMISE_KEY] = null;
        frm[LOAD_OWNER_KEY] = null;
        frm[RECOVER_KEY] = 0;
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

    function commit(frm, payload) {
        if (!frm || !frm.doc || frm.doctype !== "Door Cutting Order") return null;
        const store = storeFor(frm);
        if (!store) return null;

        const currentIdentity = identity(frm);
        const current = store.snapshot();
        if (current.identity && current.identity !== currentIdentity) return null;
        if (!payloadMatches(payload, String(frm.doc.name || ""))) return null;
        if (!current.identity) store.reset(currentIdentity);

        const snapshot = store.commit(payload);
        frm[LOADED_IDENTITY_KEY] = currentIdentity;
        frm[LOAD_PROMISE_KEY] = null;
        frm[LOAD_OWNER_KEY] = null;
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
        frm[RECOVER_KEY] = 0;
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

    function activeEditSnapshot(store, currentIdentity) {
        const current = store && store.snapshot ? store.snapshot() : null;
        return current
            && current.identity === currentIdentity
            && current.editing === true
            ? current
            : null;
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

    function abandonedLoadingSnapshot(frm, store, currentIdentity) {
        if (identity(frm) !== currentIdentity) return false;
        if (activeEditSnapshot(store, currentIdentity)) return false;
        const current = store.snapshot();
        return Boolean(current && current.status === "loading");
    }

    function recoverAbandonedLoad(frm, store, currentIdentity, result) {
        if (!abandonedLoadingSnapshot(frm, store, currentIdentity)) {
            frm[RECOVER_KEY] = 0;
            return result;
        }
        const attempts = Number(frm[RECOVER_KEY] || 0);
        if (attempts >= 2) {
            const requestId = store.beginLoad(currentIdentity);
            store.rejectLoad(
                currentIdentity,
                requestId,
                new Error("تعذر تحميل بيانات التكلفة.")
            );
            const state = store.snapshot();
            dispatch(frm, state);
            return state;
        }
        frm[RECOVER_KEY] = attempts + 1;
        return load(frm, { force: true });
    }

    async function load(frm, options = {}) {
        if (!frm || !frm.doc || frm.doctype !== "Door Cutting Order") return null;
        const store = storeFor(frm);
        const api = window.AlmdinaCostWorkspaceAPI;
        if (!store || !api || typeof api.load !== "function") return null;

        const currentIdentity = identity(frm);
        const requestToken = capture(frm);
        const editing = activeEditSnapshot(store, currentIdentity);
        if (editing) {
            // WorkspaceStore.editing is the canonical edit-session boundary.
            // A background/forced read must never replace an active draft or close
            // the session. Save/Cancel close editing first, then may request an
            // authoritative reload explicitly.
            return editing;
        }

        const orderName = String(frm.doc.name || "").trim();
        if (!orderName || (frm.is_new && frm.is_new()) || !canView(frm)) {
            return settleUnavailable(frm, store, currentIdentity);
        }

        if (!options.force && isFreshReady(frm, store, currentIdentity)) {
            return store.snapshot();
        }

        const pending = owns(frm, frm[LOAD_OWNER_KEY] || {})
            ? frm[LOAD_PROMISE_KEY] : null;
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
            if (!owns(frm, requestToken)) return snapshot(frm);
            const editingAfterFlight = activeEditSnapshot(store, currentIdentity);
            if (editingAfterFlight) return editingAfterFlight;
            if (isFreshReady(frm, store, currentIdentity)) return store.snapshot();
            return load(frm, { force: true });
        }

        const { promise, resolveFlight, rejectFlight } = createFlight(frm);

        // Install the single-flight barrier before beginLoad()/dispatch(). Both
        // are observable synchronously, so listeners must see an owned in-flight
        // request before they can re-enter this loader.
        frm[LOAD_PROMISE_KEY] = promise;
        const completed = promise.then(
            (result) => {
                if (frm[LOAD_PROMISE_KEY] === completed) {
                    frm[LOAD_PROMISE_KEY] = null;
                    frm[LOAD_OWNER_KEY] = null;
                }
                if (!owns(frm, requestToken)) return snapshot(frm);
                return recoverAbandonedLoad(frm, store, currentIdentity, result);
            },
            (error) => {
                if (frm[LOAD_PROMISE_KEY] === completed) {
                    frm[LOAD_PROMISE_KEY] = null;
                    frm[LOAD_OWNER_KEY] = null;
                }
                if (!owns(frm, requestToken)) return snapshot(frm);
                if (abandonedLoadingSnapshot(frm, store, currentIdentity)) {
                    return recoverAbandonedLoad(frm, store, currentIdentity, null);
                }
                throw error;
            }
        );
        frm[LOAD_PROMISE_KEY] = completed;
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
                // If the operator entered edit mode while this read was in flight,
                // the response is now stale relative to the local draft. Never let
                // resolveLoad() clear editing/baseline/draft in that case.
                const editingNow = activeEditSnapshot(store, currentIdentity);
                if (editingNow) return editingNow;
                if (!payloadMatches(payload, orderName)) {
                    store.rejectLoad(currentIdentity, requestId, new Error("Cost response order mismatch"));
                    const invalid = snapshot(frm);
                    if (invalid) dispatch(frm, invalid);
                    return invalid;
                }
                const accepted = store.resolveLoad(currentIdentity, requestId, payload);
                if (!accepted) return snapshot(frm);
                frm[LOADED_IDENTITY_KEY] = currentIdentity;
                // Cost GET is read-only workspace data. Never advance frm.doc.modified
                // from a read because that could hide a real concurrent DCO mutation.
                const state = store.snapshot();
                dispatch(frm, state);
                return state;
            })
            .catch((error) => {
                if (!owns(frm, requestToken)) return snapshot(frm);
                const editingNow = activeEditSnapshot(store, currentIdentity);
                if (editingNow) return editingNow;
                store.rejectLoad(currentIdentity, requestId, error);
                const state = store.snapshot();
                dispatch(frm, state);
                throw error;
            })
            .then(resolveFlight, rejectFlight);

        return completed;
    }

    function snapshot(frm) {
        const store = storeFor(frm);
        return ownedSnapshot(frm, store);
    }

    function settings(frm) {
        const state = snapshot(frm);
        const order = state && state.data && state.data.order;
        if (!order) return null;
        return {
            board_rate_usd: Number(order.board_rate_usd || 0),
            cutting_cost_per_board_usd: Number(order.cutting_cost_per_board_usd || 0),
            offcut_price_usd: Number(order.offcut_price_usd || 0),
            offcut_price_applicable: Boolean(order.offcut_price_applicable),
        };
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
            context.scheduleFrame(frm, "cost-workspace-state-load", run);
            return;
        }
        if (window.requestAnimationFrame) {
            window.requestAnimationFrame(run);
            return;
        }
        run();
    }

    const owner = Object.freeze({
        canView,
        storeFor,
        reset,
        invalidate,
        commit,
        load,
        snapshot,
        settings,
        schedule,
    });
    window.AlmdinaCostWorkspaceState = owner;

    const coordinator = window.AlmdinaWorkspaceSyncCoordinator;
    if (coordinator && typeof coordinator.register === "function") {
        coordinator.register("cost", {
            activationField: "cost_tab",
            canLoad: canView,
            invalidate,
            load,
            snapshot,
        });
    }
})();
