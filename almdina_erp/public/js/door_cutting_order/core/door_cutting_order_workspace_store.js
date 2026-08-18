(() => {
    "use strict";

    if (window.AlmdinaWorkspaceStore) return;

    function clone(value) {
        if (value === undefined) return undefined;
        if (value === null) return null;
        if (typeof structuredClone === "function") return structuredClone(value);
        return JSON.parse(JSON.stringify(value));
    }

    function freezeSnapshot(state) {
        return Object.freeze({
            kind: state.kind,
            identity: state.identity,
            status: state.status,
            data: clone(state.data),
            baseline: clone(state.baseline),
            draft: clone(state.draft),
            dirty: Boolean(state.dirty),
            editing: Boolean(state.editing),
            error: state.error,
            requestId: state.requestId,
        });
    }

    function same(left, right) {
        return JSON.stringify(left) === JSON.stringify(right);
    }

    function create(kind) {
        const listeners = new Set();
        const state = {
            kind: String(kind || "workspace"),
            identity: "",
            status: "idle",
            data: null,
            baseline: null,
            draft: null,
            dirty: false,
            editing: false,
            error: null,
            requestId: 0,
        };

        function emit() {
            const snapshot = freezeSnapshot(state);
            listeners.forEach((listener) => {
                try {
                    listener(snapshot);
                } catch (error) {
                    console.error("Almdina workspace listener failed", error);
                }
            });
            return snapshot;
        }

        function reset(identity = "") {
            state.identity = String(identity || "");
            state.status = "idle";
            state.data = null;
            state.baseline = null;
            state.draft = null;
            state.dirty = false;
            state.editing = false;
            state.error = null;
            state.requestId += 1;
            return emit();
        }

        function beginLoad(identity) {
            const normalized = String(identity || "");
            if (state.identity !== normalized) reset(normalized);
            state.status = "loading";
            state.error = null;
            state.requestId += 1;
            emit();
            return state.requestId;
        }

        function resolveLoad(identity, requestId, data) {
            if (state.identity !== String(identity || "")) return false;
            if (state.requestId !== Number(requestId)) return false;
            state.status = data == null ? "empty" : "ready";
            state.data = clone(data);
            state.baseline = null;
            state.draft = null;
            state.dirty = false;
            state.editing = false;
            state.error = null;
            emit();
            return true;
        }

        function rejectLoad(identity, requestId, error) {
            if (state.identity !== String(identity || "")) return false;
            if (state.requestId !== Number(requestId)) return false;
            state.status = "error";
            state.data = null;
            state.baseline = null;
            state.draft = null;
            state.dirty = false;
            state.editing = false;
            state.error = String(error && (error.message || error) || "تعذر تحميل البيانات.");
            emit();
            return true;
        }

        function beginEdit(seed) {
            if (state.status !== "ready" && state.status !== "empty") return false;
            const source = seed === undefined ? state.data : seed;
            state.baseline = clone(source || {});
            state.draft = clone(source || {});
            state.dirty = false;
            state.editing = true;
            emit();
            return true;
        }

        function replaceDraft(value) {
            if (!state.editing) return false;
            state.draft = clone(value || {});
            state.dirty = !same(state.baseline, state.draft);
            emit();
            return true;
        }

        function patchDraft(values) {
            if (!state.editing) return false;
            state.draft = {
                ...(state.draft || {}),
                ...clone(values || {}),
            };
            state.dirty = !same(state.baseline, state.draft);
            emit();
            return true;
        }

        function cancelEdit() {
            if (!state.editing) return false;
            state.baseline = null;
            state.draft = null;
            state.dirty = false;
            state.editing = false;
            emit();
            return true;
        }

        function commit(data) {
            state.status = data == null ? "empty" : "ready";
            state.data = clone(data);
            state.baseline = null;
            state.draft = null;
            state.dirty = false;
            state.editing = false;
            state.error = null;
            emit();
            return true;
        }

        function subscribe(listener) {
            if (typeof listener !== "function") return () => {};
            listeners.add(listener);
            return () => listeners.delete(listener);
        }

        return Object.freeze({
            snapshot: () => freezeSnapshot(state),
            reset,
            beginLoad,
            resolveLoad,
            rejectLoad,
            beginEdit,
            replaceDraft,
            patchDraft,
            cancelEdit,
            commit,
            subscribe,
        });
    }

    window.AlmdinaWorkspaceStore = Object.freeze({ create });
})();
