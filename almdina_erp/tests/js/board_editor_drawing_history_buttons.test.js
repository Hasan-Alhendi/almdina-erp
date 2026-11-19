"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.resolve(__dirname, "../..");

function load(files) {
    const context = {
        console,
        __: (message) => message,
        document: { createElementNS: () => ({ setAttribute() {}, appendChild() {} }) },
    };
    context.window = context;
    context.globalThis = context;
    vm.createContext(context);
    files.forEach((relative) => {
        vm.runInContext(fs.readFileSync(path.join(root, relative), "utf8"), context, { filename: relative });
    });
    return context.window.AlmdinaBoardEditor;
}

const editor = load([
    "public/js/board_editor/drawing_space.js",
    "public/js/board_editor/drawing_model.js",
    "public/js/board_editor/history.js",
]);
const Model = editor.DrawingModel;
const Space = editor.DrawingSpace;
const layoutHistory = editor.History.create({ pieces: { a: { local_x_mm: 10 } } });

function readySession() {
    const session = Model.createSession();
    session.activate({ pieceInstanceId: "piece:a", widthMm: 600, lengthMm: 900 });
    session.markReady();
    return session;
}

function assertRoundTrip(session, mutate, restored) {
    const saved = session.documentCanonical();
    assert.equal(session.documentDirty(), false);
    assert.equal(mutate(), true);
    assert.equal(session.documentDirty(), true);
    assert.ok(session.current().past.length > 0);
    assert.equal(session.undo(), true);
    assert.equal(session.documentCanonical(), saved);
    assert.equal(session.documentDirty(), false);
    assert.ok(session.current().future.length > 0);
    assert.equal(session.redo(), true);
    assert.equal(session.documentDirty(), true);
    restored(session);
    assert.equal(JSON.stringify(layoutHistory.get()), JSON.stringify({ pieces: { a: { local_x_mm: 10 } } }));
    assert.equal(layoutHistory.state().canUndo, false);
    assert.equal(layoutHistory.state().canRedo, false);
}

const polyline = readySession();
assertRoundTrip(polyline, () => polyline.placePoint(0, 0) && polyline.placePoint(120, 0), (session) => {
    assert.equal(session.current().document.paths.length, 1);
});

const shape = readySession();
assertRoundTrip(shape, () => shape.createShape("rectangle", {
    x_mm: 0, y_mm: 0, width_mm: 200, height_mm: 80, rotation_deg: 0,
}), (session) => {
    assert.equal(session.current().document.shapes.length, 1);
});

const pen = readySession();
const gesture = Space.createPenGesture("low");
gesture.pointerDown({ pointerId: 1, x: 0, y: 0 });
gesture.pointerMove({ pointerId: 1, x: 40, y: 0 });
const stroke = gesture.pointerUp({ pointerId: 1, x: 80, y: 10 });
assertRoundTrip(pen, () => pen.createPenPath(stroke), (session) => {
    assert.equal(session.current().document.paths.length, 1);
});

const nodes = readySession();
assert.equal(nodes.createShape("rectangle", {
    x_mm: 0, y_mm: 0, width_mm: 200, height_mm: 100, rotation_deg: 0,
}), true);
assert.equal(nodes.convertShape(nodes.current().document.shapes[0].id), true);
const nodePath = nodes.current().document.paths[0];
const node = nodePath.nodes[1];
const movedX = node.x_mm + 15;
nodes.applySave("piece:a", { ok: true, drawing_version: 1 });
assertRoundTrip(nodes, () => nodes.moveNode(nodePath.id, node.id, movedX, node.y_mm), (session) => {
    const moved = session.current().document.paths[0].nodes.find((row) => row.id === node.id);
    assert.equal(moved.x_mm, movedX);
});

const movedPath = readySession();
assert.equal(movedPath.placePoint(0, 0) && movedPath.placePoint(80, 0) && movedPath.finish(), true);
const pathId = movedPath.current().document.paths[0].id;
movedPath.applySave("piece:a", { ok: true, drawing_version: 1 });
assertRoundTrip(movedPath, () => movedPath.translatePath(pathId, 12, 6), (session) => {
    assert.equal(session.current().document.paths[0].nodes[0].x_mm, 12);
    assert.equal(session.current().document.paths[0].nodes[0].y_mm, 6);
});

const image = readySession();
assertRoundTrip(image, () => Boolean(image.addReference({
    file_id: "FILE-PRIVATE-1",
    x_mm: 0,
    y_mm: 0,
    width_mm: 100,
    height_mm: 40,
})), (session) => {
    assert.equal(session.current().document.references.length, 1);
});

const removed = readySession();
assert.equal(removed.createShape("circle", { cx_mm: 40, cy_mm: 40, radius_mm: 10 }), true);
removed.applySave("piece:a", { ok: true, drawing_version: 1 });
assertRoundTrip(removed, () => removed.deleteSelection(), (session) => {
    assert.equal(session.current().document.shapes.length, 0);
    assert.equal(session.undo(), true);
    assert.equal(session.current().document.shapes.length, 1);
});

const controller = fs.readFileSync(path.join(root, "public/js/board_editor/controller.js"), "utf8");
const historyFn = controller.slice(controller.indexOf("function applyDrawingHistory"), controller.indexOf("function drawingAction"));
assert.match(historyFn, /drawingSession\.undo\(\)/);
assert.match(historyFn, /drawingSession\.redo\(\)/);
assert.match(historyFn, /syncDrawing\(\)/);
assert.doesNotMatch(historyFn, /store\.undo|store\.redo/);
assert.match(controller, /applyDrawingHistory\(event\.shiftKey \|\| keyName\.toLowerCase\(\) === "y" \? "redo" : "undo"\)/);
assert.match(controller, /String\(event\.key\)\.toLowerCase\(\) === "z" && !event\.shiftKey/);
assert.match(controller, /if \(store\) store\.undo\(\)/);

const catalog = fs.readFileSync(path.join(root, "translations/ar.csv"), "utf8");
assert.match(catalog, /^Undo,تراجع$/m);
assert.match(catalog, /^Redo,إعادة$/m);

console.log("drawing history buttons ok");
