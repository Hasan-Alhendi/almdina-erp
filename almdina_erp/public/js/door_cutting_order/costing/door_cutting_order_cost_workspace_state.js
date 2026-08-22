(() => {
    "use strict";

    if (window.AlmdinaCostWorkspaceState) return;

    const STORE_KEY = "__almdinaCostWorkspaceStore";
    const LOAD_PROMISE_KEY = "__almdinaCostWorkspaceLoadPromise";
    const LOADED_IDENTITY_KEY = "__almdinaCostWorkspaceLoadedIdentity";

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

    function commit(frm, payload) {
        if (!frm || !frm.doc || frm.doctype !== "Door Cutting Order") return null;
        const store = storeFor(frm);
        if (!store) return null;

        const currentIdentity = identity(frm);
        const current = store.snapshot();
        if (current.identity && current.identity !== currentIdentity) return null;
        if (!current.identity) store.reset(currentIdentity);

        const snapshot = store.commit(payload);
        frm[LOADED_IDENTITY_KEY] = currentIdentity;
        frm[LOAD_PROMISE_KEY] = null;
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

    async function load(frm, options = {}) {
        if (!frm || !frm.doc || frm.doctype !== "Door Cutting Order") return null;
        const store = storeFor(frm);
        const api = window.AlmdinaCostWorkspaceAPI;
        if (!store || !api || typeof api.load !== "function") return null;

        const currentIdentity = identity(frm);
        const orderName = String(frm.doc.name || "").trim();
        if (!orderName || (frm.is_new && frm.is_new()) || !canView(frm)) {
            return settleUnavailable(frm, store, currentIdentity);
        }

        const current = store.snapshot();
        if (
            !options.force
            && frm[LOADED_IDENTITY_KEY] === currentIdentity
            && current.status === "ready"
            && current.freshness !== "stale"
        ) {
            return current;
        }
        if (!options.force && frm[LOAD_PROMISE_KEY]) return frm[LOAD_PROMISE_KEY];

        const requestId = store.beginLoad(currentIdentity);
        dispatch(frm, store.snapshot());

        const promise = api.load(orderName)
            .then((payload) => {
                if (rejectIdentityTransition(frm, store, currentIdentity)) {
                    return store.snapshot();
                }
                const accepted = store.resolveLoad(currentIdentity, requestId, payload);
                if (!accepted) return store.snapshot();
                frm[LOADED_IDENTITY_KEY] = currentIdentity;
                // Cost GET is read-only workspace data. Never advance frm.doc.modified
                // from a read because that could hide a real concurrent DCO mutation.
                const state = store.snapshot();
                dispatch(frm, state);
                return state;
            })
            .catch((error) => {
                if (rejectIdentityTransition(frm, store, currentIdentity)) {
                    return store.snapshot();
                }
                store.rejectLoad(currentIdentity, requestId, error);
                const state = store.snapshot();
                dispatch(frm, state);
                throw error;
            })
            .finally(() => {
                if (frm[LOAD_PROMISE_KEY] === promise) frm[LOAD_PROMISE_KEY] = null;
            });
        frm[LOAD_PROMISE_KEY] = promise;
        return promise;
    }

    function snapshot(frm) {
        const store = storeFor(frm);
        return store ? store.snapshot() : null;
    }

    function settings(frm) {
        const state = snapshot(frm);
        const order = state && state.data && state.data.order;
        if (!order) return null;
        return {
            board_rate_usd: Number(order.board_rate_usd || 0),
            cutting_cost_per_board_usd: Number(order.cutting_cost_per_board_usd || 0),
        };
    }

    function schedule(frm, force = false) {
        if (!frm || frm.doctype !== "Door Cutting Order") return;
        const context = documentContext();
        const run = () => {
            load(frm, { force }).catch(() => {
                // Store owns the error state. Existing presenters keep their current UX in A5.1.
            });
        };
        if (context && typeof context.scheduleFrame === "function") {
            context.scheduleFrame(frm, "cost-workspace-state-load", run);
            return;
        }
        window.requestAnimationFrame(run);
    }

    frappe.ui.form.on("Door Cutting Order", {
        onload_post_render(frm) { schedule(frm); },
        refresh(frm) { schedule(frm); },
    });

    window.addEventListener("almdina:permissions-updated", () => {
        const frm = window.cur_frm;
        if (frm && frm.doctype === "Door Cutting Order") schedule(frm, true);
    });

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
            canLoad: canView,
            invalidate,
            load,
            snapshot,
        });
    }
})();
