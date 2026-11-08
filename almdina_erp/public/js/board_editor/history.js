(() => {
    "use strict";

    function clone(value) {
        return JSON.parse(JSON.stringify(value));
    }

    function create(initialDocument) {
        let present = clone(initialDocument);
        const entry = clone(initialDocument);
        let past = [];
        let future = [];

        function get() {
            return clone(present);
        }

        function entryDocument() {
            return clone(entry);
        }

        function commit(next) {
            const serialized = JSON.stringify(next);
            if (serialized === JSON.stringify(present)) return get();
            past = [...past.slice(-79), clone(present)];
            present = clone(next);
            future = [];
            return get();
        }

        function undo() {
            if (!past.length) return get();
            future = [clone(present), ...future];
            present = past[past.length - 1];
            past = past.slice(0, -1);
            return get();
        }

        function redo() {
            if (!future.length) return get();
            past = [...past, clone(present)];
            present = future[0];
            future = future.slice(1);
            return get();
        }

        function restoreEntry() {
            return commit(entry);
        }

        function replacePresent(next) {
            // Layout-only updates (unmoved board grid) must not create history.
            present = clone(next);
            return get();
        }

        function state() {
            return Object.freeze({
                document: get(),
                canUndo: Boolean(past.length),
                canRedo: Boolean(future.length),
            });
        }

        return Object.freeze({
            get,
            entryDocument,
            commit,
            undo,
            redo,
            restoreEntry,
            replacePresent,
            state,
        });
    }

    window.AlmdinaBoardEditor = window.AlmdinaBoardEditor || {};
    window.AlmdinaBoardEditor.History = Object.freeze({ create });
})();
