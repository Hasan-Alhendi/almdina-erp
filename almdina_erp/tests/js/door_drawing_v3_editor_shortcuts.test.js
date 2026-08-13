"use strict";

const assert = require("node:assert/strict");
const path = require("node:path");

global.window = { AlmdinaDoorDrawingV3: Object.create(null) };
const root = global.window.AlmdinaDoorDrawingV3;

function freezePoint(x, y) { return Object.freeze({ x: Number(x), y: Number(y) }); }
function cloneObject(object, id = object.id) {
    return Object.freeze({
        ...object,
        id: String(id),
        geometry: Object.freeze(JSON.parse(JSON.stringify(object.geometry))),
    });
}
function translateObject(object, dx, dy) {
    const geometry = JSON.parse(JSON.stringify(object.geometry));
    if (geometry.origin) { geometry.origin.x += dx; geometry.origin.y += dy; }
    if (Array.isArray(geometry.points)) geometry.points = geometry.points.map(point => ({ x: point.x + dx, y: point.y + dy }));
    return Object.freeze({ ...object, geometry: Object.freeze(geometry) });
}

root.Geometry = Object.freeze({
    PATH_TYPE: "path",
    cloneObject,
    translateObject,
    pathSegments(object) {
        const points = object.geometry.points || [];
        return points.slice(0, Math.max(0, points.length - 1)).map((point, index) => ({ index, start: point, end: points[index + 1] }));
    },
});
root.DocumentModel = Object.freeze({
    objectById(document, id) { return (document.objects || []).find(object => String(object.id) === String(id || "")) || null; },
    addObject(document, object) { return Object.freeze({ ...document, objects: Object.freeze([...(document.objects || []), object]) }); },
});
root.ShapeView = Object.freeze({ render() {} });
root.VectorEditingView = Object.freeze({ schedule() {} });
root.BezierPathView = Object.freeze({ schedule() {} });
root.Editor = Object.freeze({ open() { return null; }, view() { return null; } });

require(path.resolve(__dirname, "../../public/js/door_drawing_v3/application/node_selection_policy.js"));
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/application/editor_shortcuts.js"));

const rectangleA = Object.freeze({ id: "a", type: "rectangle", geometry: Object.freeze({ origin: freezePoint(0, 0), widthMm: 10, heightMm: 20 }) });
const rectangleB = Object.freeze({ id: "b", type: "rectangle", geometry: Object.freeze({ origin: freezePoint(30, 10), widthMm: 15, heightMm: 15 }) });
const pathObject = Object.freeze({ id: "p", type: "path", geometry: Object.freeze({ points: Object.freeze([freezePoint(0, 0), freezePoint(50, 0), freezePoint(50, 50)]), closed: false }) });

function createHistory(initial) {
    let current = initial;
    const undoStack = [];
    const redoStack = [];
    return {
        current: () => current,
        execute(next) { undoStack.push(current); redoStack.length = 0; current = next; return current; },
        undo() { if (!undoStack.length) return current; redoStack.push(current); current = undoStack.pop(); return current; },
        redo() { if (!redoStack.length) return current; undoStack.push(current); current = redoStack.pop(); return current; },
    };
}

const initial = Object.freeze({ objects: Object.freeze([rectangleA, rectangleB, pathObject]) });
const controller = {
    root: { isConnected: true, contains: () => true },
    history: createHistory(initial),
    readOnly: false,
    selectedId: "b",
    selectedIds: ["a", "b"],
    nodeEditId: "",
    selectedNodeIndex: null,
    selectedNodeIndices: [],
    selectedSegmentIndices: [],
    dirty: false,
};

assert.equal(root.EditorShortcuts.copySelection(controller), true, "Ctrl+C policy should copy the full multi-selection");
assert.equal(root.EditorShortcuts.pasteSelection(controller), true, "Ctrl+V policy should paste a copied selection");
assert.equal(controller.history.current().objects.length, 5);
assert.equal(controller.selectedIds.length, 2, "Pasted objects should stay selected as a group");
const pasted = controller.selectedIds.map(id => root.DocumentModel.objectById(controller.history.current(), id));
assert.deepEqual(pasted.map(object => object.geometry.origin), [freezePoint(20, -20), freezePoint(50, -10)], "Paste offset should be visually down-right in the inverted-Y canvas");

assert.equal(root.EditorShortcuts.undo(controller), true, "Ctrl+Z must undo the paste command");
assert.equal(controller.history.current().objects.length, 3);
assert.deepEqual(controller.selectedIds, [], "Undo must not retain stale pasted object ids");
assert.equal(root.EditorShortcuts.redo(controller), true, "Ctrl+Y / Ctrl+Shift+Z must redo the paste command");
assert.equal(controller.history.current().objects.length, 5);

controller.selectedId = "p";
controller.selectedIds = ["p"];
controller.nodeEditId = "";
controller.tool = "select";
let prevented = false;
const enterEvent = {
    key: "Enter",
    ctrlKey: false,
    metaKey: false,
    altKey: false,
    target: null,
    preventDefault() { prevented = true; },
    stopPropagation() {},
    stopImmediatePropagation() {},
};
assert.equal(root.NodeSelectionPolicy.enterSelectedPath(controller, enterEvent), true, "Enter should open node edit mode for a selected path");
assert.equal(controller.nodeEditId, "p");
assert.equal(prevented, true);

controller.__selectionToolNodeEditSnapshot = Object.freeze({
    objectId: "p",
    selectedNodeIndex: 1,
    selectedNodeIndices: Object.freeze([1]),
    selectedSegmentIndices: Object.freeze([]),
});
controller.nodeEditId = "";
controller.selectedNodeIndex = null;
controller.selectedNodeIndices = [];
const selectButton = { dataset: { ddv3Tool: "select" } };
const selectEvent = { target: { closest: selector => selector.includes("select") ? selectButton : null } };
root.NodeSelectionPolicy.restoreNodeEdit(controller, selectEvent);
assert.equal(controller.nodeEditId, "p", "Clicking the V/select tool must preserve an active path node-edit session");
assert.deepEqual(controller.selectedNodeIndices, [1]);

console.log("Door Drawing V3 editor shortcut and node selection behavior tests passed");
