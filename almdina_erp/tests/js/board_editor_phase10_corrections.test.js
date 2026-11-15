"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.resolve(__dirname, "../..");

function load(files) {
    const context = { console, __: (message) => message };
    context.window = context;
    context.globalThis = context;
    vm.createContext(context);
    files.forEach((relative) => {
        vm.runInContext(fs.readFileSync(path.join(root, relative), "utf8"), context, { filename: relative });
    });
    return context.AlmdinaBoardEditor;
}

const editor = load([
    "public/js/board_editor/drawing_space.js",
    "public/js/board_editor/drawing_model.js",
]);
const Space = editor.DrawingSpace;
const session = editor.DrawingModel.createSession();

function ready(id, width, length) {
    session.activate({ pieceInstanceId: id, widthMm: width, lengthMm: length });
    const ticket = session.beginLoad();
    session.applyLoaded(id, ticket.token, { ok: true, drawing: null, drawing_version: 0 });
}

function lengthOf(path) {
    const from = path.nodes.find((node) => node.id === path.segments[0].from_node);
    const to = path.nodes.find((node) => node.id === path.segments[0].to_node);
    return Math.hypot(to.x_mm - from.x_mm, to.y_mm - from.y_mm);
}

function areaOf(path) {
    const nodes = path.nodes;
    let sum = 0;
    for (let index = 0; index < nodes.length; index += 1) {
        const next = nodes[(index + 1) % nodes.length];
        sum += nodes[index].x_mm * next.y_mm - next.x_mm * nodes[index].y_mm;
    }
    return Math.abs(sum) / 2;
}

ready("A", 500, 300);
assert.equal(session.anyDirty(), false);
assert.equal(session.createShape("rectangle", {
    x_mm: 10, y_mm: 20, width_mm: 80, height_mm: 40, rotation_deg: 15,
}), true);
assert.equal(session.anyDirty(), true);
const rectangle = session.current().document.shapes[0];
assert.equal(session.moveShape(rectangle.id, 25, -5), true);
const movedRectangle = session.current().document.shapes[0];
assert.equal(movedRectangle.params.x_mm, 35);
assert.equal(movedRectangle.params.y_mm, 15);
assert.equal(movedRectangle.params.width_mm, 80);
assert.equal(movedRectangle.params.height_mm, 40);
assert.equal(movedRectangle.params.rotation_deg, 15);
assert.equal(session.undo(), true);
assert.equal(session.current().document.shapes[0].params.x_mm, 10);
assert.equal(session.redo(), true);
assert.equal(session.current().document.shapes[0].params.x_mm, 35);
assert.equal(session.undo(), true);
assert.equal(session.undo(), true);
assert.equal(session.anyDirty(), false);

assert.equal(session.createShape("circle", { cx_mm: 40, cy_mm: 50, radius_mm: 12 }), true);
const circle = session.current().document.shapes[0];
session.moveShape(circle.id, 7, 9);
assert.equal(circle.params.cx_mm, 47);
assert.equal(circle.params.cy_mm, 59);
assert.equal(circle.params.radius_mm, 12);

ready("B", 400, 200);
assert.equal(session.anyDirty(), true, "the first door stays dirty after selecting another door");
assert.equal(session.createShape("circle", { cx_mm: 10, cy_mm: 10, radius_mm: 5 }), true);
assert.equal(session.moveShape(session.current().document.shapes[0].id, 7, 9), true);
session.activate({ pieceInstanceId: "A", widthMm: 500, lengthMm: 300 });
assert.equal(session.current().document.shapes.length, 1);
session.activate({ pieceInstanceId: "B", widthMm: 400, lengthMm: 200 });
assert.equal(session.current().document.shapes[0].params.cx_mm, 17);
assert.equal(session.dirtyRecords().length, 2);
session.applySave("B", { ok: false, code: "save_failed" });
assert.equal(session.anyDirty(), true);
assert.equal(session.current().messageKey, "Could not save the drawing. Your lines are still here.");
session.applySave("B", { ok: true, drawing_version: 2 });
assert.equal(session.current().drawingVersion, 2);
assert.equal(session.documentDirty(session.current()), false);
session.activate({ pieceInstanceId: "A", widthMm: 500, lengthMm: 300 });
assert.equal(session.anyDirty(), true);

const arcDocument = {
    schema: "almdina.board-editor-drawing",
    version: 1,
    units: "mm",
    coordinate_space: "door_local",
    piece_instance_id: "C",
    blank: { width_mm: 500, length_mm: 300 },
    shapes: [],
    references: [],
    paths: [{
        id: "arc-path",
        role: "manufacturing_outer",
        closed: false,
        source_shape_id: null,
        nodes: [
            { id: "n1", x_mm: 0, y_mm: 0 },
            { id: "n2", x_mm: 100, y_mm: 0 },
        ],
        segments: [{
            id: "s1",
            kind: "arc",
            from_node: "n1",
            to_node: "n2",
            radius_mm: 80,
            large_arc: false,
            sweep_clockwise: true,
        }],
    }, {
        id: "curve-path",
        role: "construction",
        closed: true,
        source_shape_id: "kept-shape",
        nodes: [
            { id: "b1", x_mm: 0, y_mm: 0 },
            { id: "b2", x_mm: 40, y_mm: 0 },
            { id: "b3", x_mm: 40, y_mm: 20 },
            { id: "b4", x_mm: 0, y_mm: 20 },
        ],
        segments: [{
            id: "bs1",
            kind: "bezier",
            from_node: "b1",
            to_node: "b2",
            controls: [{ x_mm: 10, y_mm: 15 }, { x_mm: 30, y_mm: 15 }],
        }, {
            id: "bs2", kind: "line", from_node: "b2", to_node: "b3",
        }, {
            id: "bs3", kind: "line", from_node: "b3", to_node: "b4",
        }, {
            id: "bs4", kind: "line", from_node: "b4", to_node: "b1",
        }],
    }],
};
arcDocument.shapes = [{
    id: "kept-shape",
    kind: "rectangle",
    exploded: true,
    path_id: "curve-path",
    params: { x_mm: 0, y_mm: 0, width_mm: 40, height_mm: 20, rotation_deg: 0 },
}];
ready("C", 500, 300);
const loaded = session.beginLoad();
session.applyLoaded("C", loaded.token, { ok: true, drawing: arcDocument, drawing_version: 1 });
const beforeLength = lengthOf(session.current().document.paths[0]);
const beforeArea = areaOf(session.current().document.paths[1]);
const base = {
    nodes: JSON.parse(JSON.stringify(session.current().document.paths[1].nodes)),
    segments: JSON.parse(JSON.stringify(session.current().document.paths[1].segments)),
    shapeParams: JSON.parse(JSON.stringify(session.current().document.shapes[0].params)),
};
assert.equal(session.translatePath("curve-path", 12, -4, { base }), true);
assert.equal(session.translatePath("curve-path", 12, -4, { base, history: false }), true);
const curve = session.current().document.paths[1];
assert.equal(curve.nodes[0].x_mm, 12);
assert.equal(curve.nodes[0].y_mm, -4);
assert.equal(curve.segments[0].controls[0].x_mm, 22);
assert.equal(curve.segments[0].controls[0].y_mm, 11);
assert.equal(curve.role, "construction");
assert.equal(curve.closed, true);
assert.equal(session.current().document.shapes[0].params.x_mm, 12);
assert.equal(session.current().document.shapes[0].params.width_mm, 40);
assert.equal(areaOf(curve), beforeArea);
assert.equal(session.translatePath("arc-path", 5, 6), true);
const arc = session.current().document.paths[0];
assert.equal(arc.segments[0].radius_mm, 80);
assert.equal(lengthOf(arc), beforeLength);
assert.equal(arc.role, "manufacturing_outer");
assert.equal(session.undo(), true);
assert.equal(session.current().document.paths[0].nodes[1].x_mm, 100);
assert.equal(session.redo(), true);
assert.equal(session.current().document.paths[0].nodes[1].x_mm, 105);
const pastBefore = session.current().past.length;
session.moveNode("arc-path", "n2", 5, 6);
assert.equal(session.current().past.length, pastBefore);
assert.equal(session.current().document.paths[0].nodes[1].x_mm, 105);

const frame = Space.pieceFrame({
    placement_cm: { x: 10, y: 20, w: 50, h: 30, rotated: false },
    rotation_deg: 30,
    flip_h: true,
    flip_v: true,
    sheet_no: 1,
    pivot_mm: { x: 100, y: 200 },
    entry_pivot_mm: { x: 100, y: 200 },
}, { 1: { origin_x_mm: 50, origin_y_mm: 80, trim_x_mm: 5, trim_y_mm: 5 } }, { widthMm: 500, lengthMm: 300 });
const anchor = Space.doorToWorld(frame, 10, 20);
const zoomed = Space.doorToWorld(frame, 10, 20);
zoomed.x += 20 / 2;
zoomed.y += 10 / 4;
const door = Space.worldToDoor(frame, zoomed.x, zoomed.y);
assert.notEqual(Math.round((door.x - 10) * 1000), Math.round((20 / 2) * 1000));
const turned = Space.pieceFrame({
    placement_cm: { x: 0, y: 0, w: 50, h: 30, rotated: false },
    rotation_deg: 90,
    flip_h: false,
    flip_v: false,
    sheet_no: 1,
    pivot_mm: { x: 0, y: 0 },
    entry_pivot_mm: { x: 0, y: 0 },
}, { 1: { origin_x_mm: 0, origin_y_mm: 0, trim_x_mm: 0, trim_y_mm: 0 } }, { widthMm: 500, lengthMm: 300 });
const start = Space.doorToWorld(turned, 0, 0);
const shifted = Space.worldToDoor(turned, start.x + 30, start.y);
assert.equal(Math.round(shifted.y * 1000) / 1000, 30);
assert.equal(Math.round(shifted.x * 1000) / 1000, 0);

const page = fs.readFileSync(path.join(root, "almdina_erp/page/board_editor/board_editor.js"), "utf8");
const controller = fs.readFileSync(path.join(root, "public/js/board_editor/controller.js"), "utf8");
const renderer = fs.readFileSync(path.join(root, "public/js/board_editor/canvas_renderer.js"), "utf8");
const cutSession = editor.DrawingModel.createSession();
cutSession.activate({ pieceInstanceId: "door-8", widthMm: 330, lengthMm: 550 });
const cutTicket = cutSession.beginLoad();
cutSession.applyLoaded("door-8", cutTicket.token, { ok: true, drawing: null, drawing_version: 1 });
assert.equal(cutSession.placePoint(0, 0), true);
assert.equal(cutSession.placePoint(400, 0), true);
assert.equal(cutSession.placePoint(400, 550), true);
assert.equal(cutSession.placePoint(0, 550), true);
assert.equal(cutSession.close(), true);
const cutPath = cutSession.current().document.paths[0];
assert.equal(cutSession.setPathRole(cutPath.id, "manufacturing_outer"), true);
assert.equal(cutSession.placePoint(-40, -40), true);
assert.equal(cutSession.placePoint(80, -40), true);
assert.equal(cutSession.finish(), true);
const guidePath = cutSession.current().document.paths.find((row) => row.role !== "manufacturing_outer");
assert.equal(guidePath.role, "construction");
const Compile = load(["public/js/board_editor/drawing_compile.js"]).DrawingCompile;
function compiled() {
    return Compile.compile(cutSession.current().document, 330, 550);
}
assert.equal(compiled().code, "outside_blank");
assert.equal(compiled().pathId, cutPath.id);
const beforeGuide = JSON.stringify(cutPath.nodes);
cutSession.translatePath(guidePath.id, 15, 15);
assert.equal(compiled().code, "outside_blank");
assert.equal(compiled().pathId, cutPath.id);
assert.equal(JSON.stringify(cutSession.current().document.paths.find((row) => row.id === cutPath.id).nodes), beforeGuide);
assert.equal(cutSession.setPathRole(cutPath.id, "construction"), true);
assert.equal(compiled().status, "absent");
assert.equal(cutSession.undo(), true);
assert.equal(compiled().code, "outside_blank");
const nested = Space.pieceFrame({
    placement_cm: { x: 10, y: 20, w: 55, h: 33, rotated: true },
    source_rotated_dims: true,
    rotation_deg: 0,
    flip_h: false,
    flip_v: false,
    sheet_no: 1,
    pivot_mm: { x: 375, y: 365 },
    entry_pivot_mm: { x: 375, y: 365 },
}, { 1: { origin_x_mm: 0, origin_y_mm: 0, trim_x_mm: 0, trim_y_mm: 0 } }, { widthMm: 330, lengthMm: 550 });
[[100, 200], [650, 200], [100, 530], [650, 530]].forEach(([x, y]) => {
    const local = Space.worldToDoor(nested, x, y);
    assert.ok(local.x >= -0.05 && local.x <= 330.05, `x ${local.x}`);
    assert.ok(local.y >= -0.05 && local.y <= 550.05, `y ${local.y}`);
});
const spun = Space.pieceFrame({
    placement_cm: { x: 10, y: 20, w: 55, h: 33, rotated: true },
    source_rotated_dims: true,
    rotation_deg: 30,
    flip_h: true,
    flip_v: true,
    sheet_no: 1,
    pivot_mm: { x: 375, y: 365 },
    entry_pivot_mm: { x: 375, y: 365 },
}, { 1: { origin_x_mm: 0, origin_y_mm: 0, trim_x_mm: 0, trim_y_mm: 0 } }, { widthMm: 330, lengthMm: 550 });
const spunWorld = Space.doorToWorld(spun, 10, 20);
const spunDoor = Space.worldToDoor(spun, spunWorld.x, spunWorld.y);
assert.ok(Math.abs(spunDoor.x - 10) < 0.01);
assert.ok(Math.abs(spunDoor.y - 20) < 0.01);
const plainBlank = Space.pieceFrame({
    placement_cm: { x: 0, y: 0, w: 33, h: 55, rotated: false },
    source_rotated_dims: false,
    rotation_deg: 0,
    flip_h: false,
    flip_v: false,
    sheet_no: 1,
    pivot_mm: { x: 165, y: 275 },
    entry_pivot_mm: { x: 165, y: 275 },
}, { 1: { origin_x_mm: 0, origin_y_mm: 0, trim_x_mm: 0, trim_y_mm: 0 } }, { widthMm: 330, lengthMm: 550 });
const originDoor = Space.worldToDoor(plainBlank, 0, 0);
const farDoor = Space.worldToDoor(plainBlank, 330, 550);
assert.equal(Math.round(originDoor.x), 0);
assert.equal(Math.round(originDoor.y), 0);
assert.equal(Math.round(farDoor.x), 330);
assert.equal(Math.round(farDoor.y), 550);

const chrome = load(["public/js/board_editor/canvas_renderer.js"]);
const readyBase = { createPlanInFlight: false, sourceOnly: false, canSaveLayout: true, distributionDirty: false, draftVersion: 0 };
assert.equal(chrome.CanvasRenderer.copyPlanReady({ ...readyBase, savedDrawingReady: true }), true);
assert.equal(chrome.CanvasRenderer.copyPlanReady({ ...readyBase, draftVersion: 1 }), true);
assert.equal(chrome.CanvasRenderer.copyPlanReady({ ...readyBase, distributionDirty: true, draftVersion: 1 }), true);
assert.equal(chrome.CanvasRenderer.copyPlanReady({ ...readyBase, drawingsDirty: true }), true);
assert.equal(chrome.CanvasRenderer.copyPlanReady(readyBase), false);
assert.equal(chrome.CanvasRenderer.copyPlanReady({ ...readyBase, savedDrawingReady: true, sourceOnly: true }), false);

assert.match(page, /drawing_model\.js\?v=8/);
assert.match(page, /drawing_compile\.js\?v=2/);
assert.match(page, /canvas_renderer\.js\?v=50/);
assert.match(page, /controller\.js\?v=48/);
assert.match(controller, /drawingsDirty/);
assert.match(controller, /endVectorGesture\("cancel"\)/);
assert.match(controller, /lostpointercapture/);
assert.match(controller, /pointercancel/);
assert.match(controller, /distance < 4/);
assert.match(renderer, /drawingsDirty/);
assert.match(renderer, /cursor:grab/);
assert.match(renderer, /cursor:grabbing/);
assert.doesNotMatch(renderer, /<form class="abe-path-form/);
const selectBody = controller.slice(
    controller.indexOf("function updateSelectGesture"),
    controller.indexOf("function beginNodeEdit")
);
assert.doesNotMatch(selectBody, /commitSession|distributionFingerprint/);
assert.doesNotMatch(controller, /save_board_editor_drawing|drawing_json|get_board_editor_drawing/);
