"use strict";

const assert = require("node:assert/strict");
const path = require("node:path");

global.window = {};

require(path.resolve(
    __dirname,
    "../../public/js/door_cutting_order_sketch_history.js"
));

const history = global.window.AlmdinaSketchHistory;

function apply(state, transition) {
    assert.equal(transition.changed, true, "Expected a document transition");
    return { ...state, ...transition.patch };
}

assert.equal(Object.isFrozen(history), true, "The sketch history API should be immutable");
assert.equal(history.DEFAULT_HISTORY_LIMIT, 80);

const originalElements = [{
    id: "line-1",
    type: "line",
    x1: 10,
    y1: 20,
    x2: 200,
    y2: 20,
}];
let state = history.createState(originalElements);
originalElements[0].x1 = 999;
assert.equal(state.elements[0].x1, 10, "Initial document state must own its data");
assert.deepEqual(state.undo, []);
assert.deepEqual(state.redo, []);
assert.equal(state.hasChanges, false);

const addedTransition = history.addElement(state, {
    id: "note-1",
    type: "note",
    x: 300,
    y: 160,
    text: "تعليمات",
});
state = apply(state, addedTransition);
assert.equal(state.elements.length, 2);
assert.equal(state.selectedId, "note-1");
assert.equal(state.undo.length, 1);
assert.equal(state.undo[0].length, 1);
assert.equal(state.hasChanges, true);

const selectTransition = history.selectElement(state, "line-1");
state = apply(state, selectTransition);
assert.equal(selectTransition.selected.id, "line-1");
assert.equal(state.selectedId, "line-1");

state = apply(state, history.deleteSelected(state));
assert.deepEqual(state.elements.map(element => element.id), ["note-1"]);
assert.equal(state.selectedId, "");
assert.equal(state.undo.length, 2);

state = apply(state, history.undo(state));
assert.deepEqual(state.elements.map(element => element.id), ["line-1", "note-1"]);
assert.equal(state.selectedId, "", "Undo should not invent a selection after deletion");
assert.equal(state.redo.length, 1);

state = apply(state, history.redo(state));
assert.deepEqual(state.elements.map(element => element.id), ["note-1"]);
assert.equal(state.selectedId, "", "Redo should clear a selection removed by the change");

state = apply(state, history.clear(state));
assert.deepEqual(state.elements, []);
assert.equal(history.clear(state).changed, false, "Clearing an empty document is a no-op");
state = apply(state, history.undo(state));
assert.deepEqual(state.elements.map(element => element.id), ["note-1"]);

let limited = history.createState([]);
for (let index = 0; index < 4; index += 1) {
    limited = apply(
        limited,
        history.snapshot(limited, [{ id: `line-${index}` }], 2)
    );
}
assert.equal(limited.undo.length, 2, "History should retain only the configured limit");
assert.equal(limited.undo[0][0].id, "line-2");
assert.equal(limited.undo[1][0].id, "line-3");

const missingSelection = history.selectElement(state, "missing");
state = apply(state, missingSelection);
assert.equal(missingSelection.selected, null);
assert.equal(state.selectedId, "");

assert.equal(history.deleteSelected(state).changed, false);
assert.equal(history.undo(history.createState([])).changed, false);
assert.equal(history.redo(history.createState([])).changed, false);
assert.equal(history.addElement(state, null).changed, false);

console.log("Pure special-shape document history checks passed");
