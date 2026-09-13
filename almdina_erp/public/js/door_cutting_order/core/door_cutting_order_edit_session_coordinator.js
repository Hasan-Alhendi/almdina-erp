(() => {
    "use strict";

    if (window.AlmdinaDcoEditSessionCoordinator) return;

    const DOCTYPE = "Door Cutting Order";
    const KINDS = new Set(["order", "plan", "cost"]);
    const states = new WeakMap();
    const adapters = new Map();

    function documentContext() {
        return window.AlmdinaDocumentContext || null;
    }

    function capture(frm) {
        const context = documentContext();
        if (context && typeof context.capture === "function") return context.capture(frm);
        if (!frm || !frm.doc) return null;
        return Object.freeze({
            identity: `${frm.doctype || frm.doc.doctype || ""}::${frm.doc.name || "__new__"}`,
            generation: 0,
        });
    }

    function sameToken(left, right) {
        return Boolean(
            left && right
            && left.identity === right.identity
            && Number(left.generation) === Number(right.generation)
        );
    }

    function isCurrent(frm, token) {
        const context = documentContext();
        if (context && typeof context.isCurrent === "function") {
            return context.isCurrent(frm, token);
        }
        return Boolean(window.cur_frm === frm && sameToken(capture(frm), token));
    }

    function emptyState(token = null) {
        return {
            token,
            activeKind: null,
            phase: "idle",
            sessionGeneration: 0,
        };
    }

    function stateFor(frm) {
        if (!frm || !frm.doc || frm.doctype !== DOCTYPE) return null;
        const token = capture(frm);
        let state = states.get(frm);
        if (!state || !sameToken(state.token, token)) {
            state = emptyState(token);
            states.set(frm, state);
        }
        return state;
    }

    function snapshot(frm) {
        const state = stateFor(frm) || emptyState();
        return Object.freeze({
            activeKind: state.activeKind,
            phase: state.phase,
            documentIdentity: state.token && state.token.identity || "",
            documentGeneration: state.token && Number(state.token.generation) || 0,
            sessionGeneration: state.sessionGeneration,
            editing: state.phase === "editing",
        });
    }

    function emit(frm, state) {
        if (!isCurrent(frm, state.token)) return false;
        if (typeof frm.trigger === "function") frm.trigger("almdina_edit_session_changed");
        return true;
    }

    function transitionCurrent(frm, state, token, change) {
        if (states.get(frm) !== state || !sameToken(state.token, token) || !isCurrent(frm, token)) {
            return false;
        }
        Object.assign(state, change);
        emit(frm, state);
        return true;
    }

    function validKind(kind) {
        return KINDS.has(String(kind || ""));
    }

    function register(kind, adapter) {
        const normalized = String(kind || "");
        if (!validKind(normalized) || !adapter) return false;
        adapters.set(normalized, Object.freeze({ ...adapter }));
        return true;
    }

    function adapterFor(kind) {
        return adapters.get(String(kind || "")) || null;
    }

    function canStart(frm, kind) {
        const state = stateFor(frm);
        const adapter = adapterFor(kind);
        if (!state || !adapter || state.phase !== "idle") return false;
        return typeof adapter.canStart !== "function" || adapter.canStart(frm) === true;
    }

    async function run(frm, kind, command, intermediatePhase) {
        const state = stateFor(frm);
        const adapter = adapterFor(kind);
        if (!state || !adapter || !validKind(kind)) return false;
        const token = state.token;
        const generation = state.sessionGeneration + (command === "start" ? 1 : 0);

        if (command === "start") {
            if (state.phase !== "idle" || (typeof adapter.canStart === "function" && adapter.canStart(frm) !== true)) return false;
            if (!transitionCurrent(frm, state, token, {
                activeKind: kind,
                phase: intermediatePhase,
                sessionGeneration: generation,
            })) return false;
        } else {
            if (state.activeKind !== kind || state.phase !== "editing") return false;
            if (!transitionCurrent(frm, state, token, { phase: intermediatePhase })) return false;
        }

        const operation = adapter[command];
        if (typeof operation !== "function") {
            transitionCurrent(frm, state, token, command === "start"
                ? { activeKind: null, phase: "idle" }
                : { phase: "editing" });
            return false;
        }

        try {
            const result = await Promise.resolve(operation(frm, Object.freeze({
                kind,
                document: token,
                sessionGeneration: state.sessionGeneration,
            })));
            if (states.get(frm) !== state || !sameToken(state.token, token) || !isCurrent(frm, token)) return false;
            if (result === false) {
                transitionCurrent(frm, state, token, command === "start"
                    ? { activeKind: null, phase: "idle" }
                    : { phase: "editing" });
                return false;
            }
            transitionCurrent(frm, state, token, { activeKind: command === "start" ? kind : null, phase: command === "start" ? "editing" : "idle" });
            return true;
        } catch (error) {
            if (states.get(frm) === state && sameToken(state.token, token) && isCurrent(frm, token)) {
                transitionCurrent(frm, state, token, command === "start"
                    ? { activeKind: null, phase: "idle" }
                    : { phase: "editing" });
            }
            throw error;
        }
    }

    function start(frm, kind) { return run(frm, String(kind || ""), "start", "starting"); }
    function save(frm, kind) { return run(frm, String(kind || ""), "save", "saving"); }
    function cancel(frm, kind) { return run(frm, String(kind || ""), "cancel", "cancelling"); }

    // Compatibility projections are one-way: legacy feature-local flags may be
    // updated by the registered adapter, but they never answer coordinator state.
    function isEditing(frm, kind) {
        const state = stateFor(frm);
        return Boolean(state && state.phase === "editing" && state.activeKind === kind);
    }

    function activeEditingKind(frm) {
        const state = stateFor(frm);
        return state && state.phase === "editing" ? state.activeKind : null;
    }

    function activeKind(frm) {
        const state = stateFor(frm);
        return state && state.phase !== "idle" ? state.activeKind : null;
    }

    // Adapters receive this predicate with their command context. It intentionally
    // reads the existing state without calling stateFor(): a Form instance may be
    // reused for another DCO while an old async operation is still resolving.
    function isSessionCurrent(frm, sessionContext) {
        const state = states.get(frm);
        const context = sessionContext || {};
        return Boolean(
            state
            && validKind(context.kind)
            && state.activeKind === context.kind
            && state.sessionGeneration === Number(context.sessionGeneration)
            && sameToken(state.token, context.document)
            && isCurrent(frm, context.document)
        );
    }

    // One explicit migration seam for pre-coordinator Order checkpoint recovery.
    // It accepts a known feature projection during form hydration; normal runtime
    // state is never inferred by polling adapters or presentation owners.
    function adoptLegacyEditing(frm, kind) {
        const state = stateFor(frm);
        if (!state || !validKind(kind) || state.phase !== "idle") return false;
        state.activeKind = kind;
        state.phase = "editing";
        state.sessionGeneration += 1;
        emit(frm, state);
        return true;
    }

    window.AlmdinaDcoEditSessionCoordinator = Object.freeze({
        register,
        snapshot,
        canStart,
        start,
        save,
        cancel,
        isEditing,
        activeKind,
        activeEditingKind,
        isSessionCurrent,
        adoptLegacyEditing,
    });
})();
