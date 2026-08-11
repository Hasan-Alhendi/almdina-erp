(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV2 = window.AlmdinaDoorDrawingV2 || Object.create(null);
    const documents = root.DocumentModel;
    if (!documents) throw new Error("Door Drawing V2 DocumentModel must load before SelectionManager");

    function normalizeIds(ids) {
        const result = [];
        const seen = new Set();
        (Array.isArray(ids) ? ids : []).forEach(value => {
            const id = String(value || "");
            if (!id || seen.has(id)) return;
            seen.add(id);
            result.push(id);
        });
        return result;
    }

    function create(ids = [], anchorId = "") {
        const normalized = normalizeIds(ids);
        const requestedAnchor = String(anchorId || "");
        const anchor = normalized.includes(requestedAnchor)
            ? requestedAnchor
            : normalized[normalized.length - 1] || "";
        return Object.freeze({ ids: Object.freeze(normalized), anchorId: anchor });
    }

    function clear() {
        return create();
    }

    function selectOnly(state, objectId) {
        const id = String(objectId || "");
        return id ? create([id], id) : clear();
    }

    function add(state, objectId) {
        const id = String(objectId || "");
        if (!id) return create(state && state.ids, state && state.anchorId);
        return create([...(state && state.ids || []), id], id);
    }

    function remove(state, objectId) {
        const id = String(objectId || "");
        return create((state && state.ids || []).filter(item => item !== id));
    }

    function toggle(state, objectId) {
        const id = String(objectId || "");
        if (!id) return clear();
        return (state && state.ids || []).includes(id)
            ? remove(state, id)
            : add(state, id);
    }

    function setMany(ids, anchorId = "") {
        return create(ids, anchorId);
    }

    function isSelected(state, objectId) {
        return Boolean(state && state.ids && state.ids.includes(String(objectId || "")));
    }

    function selectedObjects(document, state) {
        const parsed = documents.parse(document);
        const selected = new Set(state && state.ids || []);
        return parsed.objects.filter(object => selected.has(object.id));
    }

    function prune(document, state) {
        const parsed = documents.parse(document);
        const valid = new Set(parsed.objects.map(object => object.id));
        return create(
            (state && state.ids || []).filter(id => valid.has(id)),
            state && state.anchorId
        );
    }

    function selectionChanged(first, second) {
        const a = create(first && first.ids, first && first.anchorId);
        const b = create(second && second.ids, second && second.anchorId);
        if (a.anchorId !== b.anchorId || a.ids.length !== b.ids.length) return true;
        return a.ids.some((id, index) => id !== b.ids[index]);
    }

    root.SelectionManager = Object.freeze({
        create,
        clear,
        selectOnly,
        add,
        remove,
        toggle,
        setMany,
        isSelected,
        selectedObjects,
        prune,
        selectionChanged,
    });
})();
