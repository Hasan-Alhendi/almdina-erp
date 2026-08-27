(() => {
    "use strict";
    const root = window.AlmdinaSpecialShapeDocumentation = window.AlmdinaSpecialShapeDocumentation || Object.create(null);
    function create(initial) {
        const doc = root.Document;
        if (!doc) throw new Error("Special-shape document contract is unavailable");
        let present = doc.clone(initial);
        let baseline = doc.toStored(present);
        let past = [];
        let future = [];
        function commit(next) {
            const serialized = doc.toStored(next);
            if (serialized === doc.toStored(present)) return present;
            past = [...past.slice(-49), doc.clone(present)];
            present = doc.clone(next);
            future = [];
            return get();
        }
        function undo() { if (!past.length) return get(); future = [doc.clone(present), ...future]; present = past[past.length - 1]; past = past.slice(0, -1); return get(); }
        function redo() { if (!future.length) return get(); past = [...past, doc.clone(present)]; present = future[0]; future = future.slice(1); return get(); }
        function get() { return doc.clone(present); }
        function markSaved(savedDocument = present) { baseline = doc.toStored(savedDocument); }
        function isDirty() { return doc.toStored(present) !== baseline; }
        function state() { return Object.freeze({ document: get(), canUndo: Boolean(past.length), canRedo: Boolean(future.length), dirty: isDirty() }); }
        return Object.freeze({ commit, undo, redo, get, markSaved, isDirty, state });
    }
    root.History = Object.freeze({ create });
})();
