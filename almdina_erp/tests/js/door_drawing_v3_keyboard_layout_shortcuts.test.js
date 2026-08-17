"use strict";

const assert = require("node:assert/strict");
const path = require("node:path");

global.window = { AlmdinaDoorDrawingV3: Object.create(null) };
const root = global.window.AlmdinaDoorDrawingV3;

function cloneObject(object, id = object.id) {
    return Object.freeze({ ...object, id: String(id), geometry: Object.freeze(JSON.parse(JSON.stringify(object.geometry))) });
}
function translateObject(object, dx, dy) {
    const geometry = JSON.parse(JSON.stringify(object.geometry));
    if (geometry.origin) { geometry.origin.x += dx; geometry.origin.y += dy; }
    return Object.freeze({ ...object, geometry: Object.freeze(geometry) });
}
root.Geometry = Object.freeze({ cloneObject, translateObject });
root.DocumentModel = Object.freeze({
    objectById(document, id) { return (document.objects || []).find(object => String(object.id) === String(id || "")) || null; },
    addObject(document, object) { return Object.freeze({ ...document, objects: Object.freeze([...(document.objects || []), object]) }); },
    removeObject(document, id) { return Object.freeze({ ...document, objects: Object.freeze((document.objects || []).filter(object => String(object.id) !== String(id))) }); },
});
root.ShapeView = Object.freeze({ render() {} });
root.VectorEditingView = Object.freeze({ schedule() {} });
root.BezierPathView = Object.freeze({ schedule() {} });
root.Editor = Object.freeze({ open() { return null; }, view() { return null; } });

require(path.resolve(__dirname, "../../public/js/door_drawing_v3/application/editor_shortcuts.js"));

function history(initial) {
    let current = initial;
    const undo = [];
    const redo = [];
    return {
        current: () => current,
        execute(next) { undo.push(current); redo.length = 0; current = next; return current; },
        undo() { if (!undo.length) return current; redo.push(current); current = undo.pop(); return current; },
        redo() { if (!redo.length) return current; undo.push(current); current = redo.pop(); return current; },
    };
}

function event(key, code, options = {}) {
    const state = { prevented: false, stopped: false, immediate: false };
    return {
        key,
        code,
        ctrlKey: options.ctrlKey !== false,
        metaKey: Boolean(options.metaKey),
        altKey: Boolean(options.altKey),
        shiftKey: Boolean(options.shiftKey),
        target: null,
        preventDefault() { state.prevented = true; },
        stopPropagation() { state.stopped = true; },
        stopImmediatePropagation() { state.immediate = true; },
        state,
    };
}

const a = Object.freeze({ id: "a", type: "rectangle", geometry: Object.freeze({ origin: { x: 0, y: 0 }, widthMm: 10, heightMm: 20 }) });
const b = Object.freeze({ id: "b", type: "rectangle", geometry: Object.freeze({ origin: { x: 40, y: 0 }, widthMm: 10, heightMm: 20 }) });
const controller = {
    root: { isConnected: true, contains: () => false },
    history: history(Object.freeze({ objects: Object.freeze([a, b]) })),
    readOnly: false,
    selectedId: "a",
    selectedIds: ["a"],
    selectedNodeIndices: [],
    selectedSegmentIndices: [],
    dirty: false,
};

assert.equal(root.EditorShortcuts.shortcutKey(event("ؤ", "KeyC")), "c", "Physical KeyC must win over Arabic keyboard text");
assert.equal(root.EditorShortcuts.shortcutKey(event("ر", "KeyV")), "v");
assert.equal(root.EditorShortcuts.shortcutKey(event("ئ", "KeyZ")), "z");
assert.equal(root.EditorShortcuts.shortcutKey(event("غ", "KeyY")), "y");

const copy = event("ؤ", "KeyC");
assert.equal(root.EditorShortcuts.keyDown(controller, copy), true, "Ctrl+C must work while Arabic layout is active");
assert.equal(copy.state.prevented, true);

const paste = event("ر", "KeyV");
assert.equal(root.EditorShortcuts.keyDown(controller, paste), true, "Ctrl+V must work while Arabic layout is active");
assert.equal(controller.history.current().objects.length, 3);

const undo = event("ئ", "KeyZ");
assert.equal(root.EditorShortcuts.keyDown(controller, undo), true, "Ctrl+Z must use physical KeyZ");
assert.equal(controller.history.current().objects.length, 2);

const redo = event("غ", "KeyY");
assert.equal(root.EditorShortcuts.keyDown(controller, redo), true, "Ctrl+Y must use physical KeyY");
assert.equal(controller.history.current().objects.length, 3);

controller.selectedId = "a";
controller.selectedIds = ["a"];
const cut = event("ء", "KeyX");
assert.equal(root.EditorShortcuts.keyDown(controller, cut), true, "Ctrl+X must cut the current selection on Arabic layout");
assert.equal(controller.history.current().objects.length, 2);

const selectAll = event("ش", "KeyA");
assert.equal(root.EditorShortcuts.keyDown(controller, selectAll), true, "Ctrl+A must select all drawing objects");
assert.equal(controller.selectedIds.length, 2);

const duplicate = event("ي", "KeyD");
assert.equal(root.EditorShortcuts.keyDown(controller, duplicate), true, "Ctrl+D must duplicate selection independent of layout");
assert.equal(controller.history.current().objects.length, 4);

console.log("Door Drawing V3 keyboard-layout independent shortcut tests passed");
