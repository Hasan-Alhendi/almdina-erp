(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV4 = window.AlmdinaDoorDrawingV4 || Object.create(null);

    const DEFAULT_LIMIT = 100;

    function create(options = {}) {
        const limit = Math.max(1, Number(options.limit) || DEFAULT_LIMIT);
        let past = [];
        let future = [];

        function snapshot() {
            return Object.freeze({
                canUndo: past.length > 0,
                canRedo: future.length > 0,
                undoCount: past.length,
                redoCount: future.length,
            });
        }

        function record(before, after, label = "edit") {
            if (!before || !after || before === after) return snapshot();
            past = [...past, Object.freeze({ before, after, label: String(label) })].slice(-limit);
            future = [];
            return snapshot();
        }

        function undo(current) {
            if (!past.length) return Object.freeze({ changed: false, document: current, ...snapshot() });
            const entry = past[past.length - 1];
            past = past.slice(0, -1);
            future = [...future, entry].slice(-limit);
            return Object.freeze({ changed: true, document: entry.before, label: entry.label, ...snapshot() });
        }

        function redo(current) {
            if (!future.length) return Object.freeze({ changed: false, document: current, ...snapshot() });
            const entry = future[future.length - 1];
            future = future.slice(0, -1);
            past = [...past, entry].slice(-limit);
            return Object.freeze({ changed: true, document: entry.after, label: entry.label, ...snapshot() });
        }

        function clear() {
            past = [];
            future = [];
            return snapshot();
        }

        return Object.freeze({ snapshot, record, undo, redo, clear });
    }

    root.CommandHistory = Object.freeze({ DEFAULT_LIMIT, create });
})();