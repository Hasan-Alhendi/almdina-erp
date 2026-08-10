(() => {
    "use strict";

    const DEFAULT_HISTORY_LIMIT = 80;
    let activeState = null;

    function clone(value) {
        return JSON.parse(JSON.stringify(value));
    }

    function elementsOf(value) {
        return Array.isArray(value) ? value : [];
    }

    function historyOf(value) {
        return Array.isArray(value) ? value : [];
    }

    function result(changed, patch = {}, selected = null) {
        return { changed, patch, selected };
    }

    function createState(elements = []) {
        activeState = {
            elements: clone(elementsOf(elements)),
            undo: [],
            redo: [],
            selectedId: "",
            hasChanges: false,
        };
        return activeState;
    }

    function getActiveState() {
        return activeState;
    }

    function clearActiveState(state = null) {
        if (!state || activeState === state) activeState = null;
    }

    function snapshot(state, elements = state && state.elements, limit = DEFAULT_HISTORY_LIMIT) {
        const safeLimit = Math.max(1, Math.floor(Number(limit) || DEFAULT_HISTORY_LIMIT));
        const undo = historyOf(state && state.undo).slice();
        undo.push(clone(elementsOf(elements)));
        if (undo.length > safeLimit) undo.splice(0, undo.length - safeLimit);
        return result(true, {
            undo,
            redo: [],
            hasChanges: true,
        });
    }

    function addElement(state, element, limit = DEFAULT_HISTORY_LIMIT) {
        if (!element || typeof element !== "object" || !element.id) {
            return result(false);
        }
        const history = snapshot(state, state && state.elements, limit);
        return result(true, {
            ...history.patch,
            elements: [
                ...clone(elementsOf(state && state.elements)),
                clone(element),
            ],
            selectedId: String(element.id),
            draft: null,
        }, clone(element));
    }

    function selectElement(state, elementId) {
        const selected = elementsOf(state && state.elements).find(
            element => String(element && element.id) === String(elementId || "")
        ) || null;
        return result(true, {
            selectedId: selected ? String(selected.id) : "",
        }, selected);
    }

    function deleteSelected(state, limit = DEFAULT_HISTORY_LIMIT) {
        const selectedId = String(state && state.selectedId || "");
        const elements = elementsOf(state && state.elements);
        const index = elements.findIndex(
            element => String(element && element.id) === selectedId
        );
        if (!selectedId || index < 0) return result(false);
        const history = snapshot(state, elements, limit);
        return result(true, {
            ...history.patch,
            elements: clone(elements.filter((element, elementIndex) =>
                elementIndex !== index
            )),
            selectedId: "",
        });
    }

    function clear(state, limit = DEFAULT_HISTORY_LIMIT) {
        const elements = elementsOf(state && state.elements);
        if (!elements.length) return result(false);
        const history = snapshot(state, elements, limit);
        return result(true, {
            ...history.patch,
            elements: [],
            selectedId: "",
            draft: null,
        });
    }

    function validSelection(elements, selectedId) {
        const safeId = String(selectedId || "");
        return safeId && elements.some(
            element => String(element && element.id) === safeId
        ) ? safeId : "";
    }

    function undo(state) {
        const past = historyOf(state && state.undo).slice();
        if (!past.length) return result(false);
        const elements = clone(elementsOf(past.pop()));
        const future = historyOf(state && state.redo).slice();
        future.push(clone(elementsOf(state && state.elements)));
        return result(true, {
            elements,
            undo: past,
            redo: future,
            selectedId: validSelection(elements, state && state.selectedId),
            hasChanges: true,
        });
    }

    function redo(state) {
        const future = historyOf(state && state.redo).slice();
        if (!future.length) return result(false);
        const elements = clone(elementsOf(future.pop()));
        const past = historyOf(state && state.undo).slice();
        past.push(clone(elementsOf(state && state.elements)));
        return result(true, {
            elements,
            undo: past,
            redo: future,
            selectedId: validSelection(elements, state && state.selectedId),
            hasChanges: true,
        });
    }

    window.AlmdinaSketchHistory = Object.freeze({
        DEFAULT_HISTORY_LIMIT,
        createState,
        getActiveState,
        clearActiveState,
        snapshot,
        addElement,
        selectElement,
        deleteSelected,
        clear,
        undo,
        redo,
    });
})();
