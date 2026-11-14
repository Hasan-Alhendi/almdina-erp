"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.resolve(__dirname, "../..");

function load(files, contextExtras) {
    const context = Object.assign({
        console,
        __: (message) => message,
        document: { createElementNS() { return { setAttribute() {}, appendChild() {} }; } },
    }, contextExtras || {});
    context.window = context;
    context.globalThis = context;
    vm.createContext(context);
    files.forEach((relative) => {
        vm.runInContext(fs.readFileSync(path.join(root, relative), "utf8"), context, { filename: relative });
    });
    return context;
}

const editor = load([
    "public/js/board_editor/drawing_space.js",
    "public/js/board_editor/drawing_model.js",
]).AlmdinaBoardEditor;
const Space = editor.DrawingSpace;
const Model = editor.DrawingModel;

function session() {
    const drawing = Model.createSession();
    drawing.activate({ pieceInstanceId: "piece:special", widthMm: 600, lengthMm: 2100 });
    drawing.markReady();
    return drawing;
}

function stroke(points, level, options) {
    return Space.fitPenStroke(points, level || "low", options);
}

function linePoints(count, jitter) {
    const points = [];
    for (let index = 0; index <= count; index += 1) {
        points.push({ x: index, y: jitter ? (index % 2) * jitter : 0 });
    }
    return points;
}

const straight = stroke(linePoints(100, 0.04), "low");
assert.equal(straight.ok, true);
assert.equal(straight.parts.closed, false);
assert.equal(straight.parts.segments.length, 1);
assert.equal(straight.parts.segments[0].kind, "line");
assert.equal(straight.parts.nodes[0].x_mm, 0);
assert.equal(straight.parts.nodes[0].y_mm, 0);
assert.equal(straight.parts.nodes[1].x_mm, 100);
assert.ok(straight.stats.maxErrorMm <= 0.3);
assert.equal(straight.suggestClose, false);

const corner = [];
for (let x = 0; x <= 50; x += 1) corner.push({ x, y: 0 });
for (let y = 1; y <= 50; y += 1) corner.push({ x: 50, y });
const sharp = stroke(corner, "low");
assert.equal(sharp.parts.segments.map((segment) => segment.kind).join(","), "line,line");
assert.ok(sharp.parts.nodes.some((node) => node.x_mm === 50 && node.y_mm === 0));
assert.equal(sharp.parts.nodes[0].x_mm, 0);
assert.equal(sharp.parts.nodes[sharp.parts.nodes.length - 1].y_mm, 50);
assert.ok(sharp.stats.maxErrorMm < 0.05);

const arc = [];
for (let degree = 0; degree <= 90; degree += 1) {
    const angle = degree * Math.PI / 180;
    arc.push({ x: 100 + Math.cos(angle) * 80, y: 100 + Math.sin(angle) * 80 });
}
const curve = stroke(arc, "low");
assert.equal(curve.ok, true);
assert.ok(curve.parts.segments.every((segment) => segment.kind === "bezier" && segment.controls.length === 2));
assert.ok(curve.stats.nodes < arc.length);
assert.ok(curve.stats.maxErrorMm <= 0.55);
assert.ok(Math.abs(curve.parts.nodes[0].x_mm - 180) < 0.01);
assert.ok(Math.abs(curve.parts.nodes[0].y_mm - 100) < 0.01);
assert.ok(Math.abs(curve.parts.nodes[curve.parts.nodes.length - 1].x_mm - 100) < 0.01);
assert.ok(Math.abs(curve.parts.nodes[curve.parts.nodes.length - 1].y_mm - 180) < 0.01);

const sine = [];
for (let x = 0; x <= 200; x += 1) sine.push({ x, y: Math.sin((x / 200) * Math.PI * 2) * 30 });
const off = stroke(sine, "off");
const low = stroke(sine, "low");
const high = stroke(sine, "high");
assert.ok(off.stats.nodes > low.stats.nodes);
assert.ok(low.stats.nodes > high.stats.nodes);
assert.ok(off.stats.maxErrorMm < high.stats.maxErrorMm);
assert.ok(high.stats.maxErrorMm <= 1.8);
assert.equal(Space.fitPenStroke(sine, "low").stats.nodes, low.stats.nodes);

assert.equal(stroke([{ x: 0, y: 0 }, { x: 0.05, y: 0 }], "off").ok, false);
const noisy = [];
for (let index = 0; index <= 40; index += 1) {
    noisy.push({ x: index, y: 0 }, { x: index, y: 0 }, { x: index + 0.01, y: 0 });
}
const cleaned = stroke(noisy, "low");
assert.equal(cleaned.parts.segments.length, 1);
cleaned.parts.segments.forEach((segment) => {
    assert.notEqual(segment.from, segment.to);
});

const many = [];
for (let index = 0; index < 7000; index += 1) many.push({ x: index * 0.2, y: (index % 5) * 0.02 });
const longStroke = stroke(many, "medium");
assert.equal(longStroke.ok, true);
assert.ok(longStroke.stats.nodes < 20);
assert.equal(longStroke.parts.nodes[0].x_mm, 0);
assert.equal(longStroke.parts.nodes[longStroke.parts.nodes.length - 1].x_mm, 1399.8);

const gesture = Space.createPenGesture("low");
assert.equal(gesture.pointerDown({ pointerId: 4, x: 0, y: 0 }), true);
assert.equal(gesture.pointerMove({ pointerId: 4, x: 0.05, y: 0 }), false);
assert.equal(gesture.preview().length, 1);
assert.equal(gesture.pointerMove({ pointerId: 8, x: 30, y: 12 }), false);
assert.equal(gesture.preview().length, 1);
assert.equal(gesture.pointerMove({ pointerId: 4, x: 20, y: 0 }), true);
assert.equal(gesture.active(), true);
const drawn = session();
assert.equal(drawn.current().document.paths.length, 0);
const committed = gesture.pointerUp({ pointerId: 4, x: 80, y: 0 });
assert.equal(committed.ok, true);
assert.equal(gesture.pointerUp({ pointerId: 4, x: 90, y: 0 }), null);
assert.equal(drawn.createPenPath(committed), true);
assert.equal(drawn.current().document.paths.length, 1);
assert.equal(drawn.current().past.length, 1);
const beforeUndo = JSON.stringify(drawn.current().document);
drawn.undo();
assert.equal(drawn.current().document.paths.length, 0);
drawn.redo();
assert.equal(JSON.stringify(drawn.current().document), beforeUndo);

const cancelled = Space.createPenGesture("low");
cancelled.pointerDown({ pointerId: 2, x: 1, y: 1 });
cancelled.pointerMove({ pointerId: 2, x: 15, y: 4 });
assert.equal(cancelled.pointerCancel({ pointerId: 2 }), true);
assert.equal(cancelled.pointerUp({ pointerId: 2, x: 30, y: 6 }), null);
const escaped = Space.createPenGesture("high");
escaped.pointerDown({ pointerId: 5, x: 0, y: 0 });
escaped.cancel();
assert.equal(escaped.active(), false);
assert.equal(escaped.pointerUp({ pointerId: 5, x: 10, y: 0 }), null);

const pen = session();
assert.equal(pen.createShape("rectangle", {
    x_mm: 10, y_mm: 20, width_mm: 500, height_mm: 300, rotation_deg: 0,
}), true);
assert.equal(pen.createPenPath(straight), true);
assert.equal(pen.current().document.shapes[0].params.width_mm, 500);
assert.equal(pen.current().document.paths.length, 1);
assert.equal(pen.current().document.paths[0].role, "construction");
assert.equal(pen.current().document.paths[0].source_shape_id, null);
assert.equal(pen.placePoint(5, 5), true);
assert.equal(pen.placePoint(5, 40), true);
assert.equal(pen.current().document.paths.length, 2);
assert.equal(pen.current().document.paths[0].nodes.length, 2);

const curved = session();
assert.equal(curved.createPenPath(curve), true);
const curvePath = curved.current().document.paths[0];
const control = curvePath.segments[0].controls[0].y_mm;
assert.equal(curved.moveBezierControl(curvePath.id, curvePath.segments[0].id, 0, curvePath.segments[0].controls[0].x_mm, control + 4), true);
assert.equal(curved.current().document.paths[0].segments[0].controls[0].y_mm, control + 4);
curved.undo();
assert.equal(curved.current().document.paths[0].segments[0].controls[0].y_mm, control);
assert.equal(curved.selectHit({ x: curvePath.nodes[0].x_mm, y: curvePath.nodes[0].y_mm }, 2), true);
assert.equal(curved.current().selection.pathId, curvePath.id);

const editable = session();
assert.equal(editable.createPenPath(sharp), true);
const cornerPath = editable.current().document.paths[0];
const middle = cornerPath.nodes[1];
assert.equal(editable.moveNode(cornerPath.id, middle.id, 54, 2), true);
assert.equal(editable.current().document.paths[0].segments[0].to_node, middle.id);
assert.equal(editable.current().document.paths[0].segments[1].from_node, middle.id);
assert.equal(editable.deleteNode(cornerPath.id, middle.id), true);
assert.equal(editable.current().document.paths[0].nodes.length, 2);
assert.equal(editable.current().document.paths[0].segments.length, 1);
assert.equal(editable.current().document.paths[0].segments[0].from_node, editable.current().document.paths[0].nodes[0].id);
assert.equal(editable.current().document.paths[0].segments[0].to_node, editable.current().document.paths[0].nodes[1].id);

const loop = [];
for (let index = 0; index < 36; index += 1) {
    const angle = (index / 36) * Math.PI * 2;
    loop.push({ x: 80 + Math.cos(angle) * 30, y: 80 + Math.sin(angle) * 30 });
}
loop.push({ x: loop[0].x + 1.5, y: loop[0].y + 0.2 });
const almost = stroke(loop, "low");
assert.equal(almost.ok, true);
assert.equal(almost.suggestClose, true);
assert.equal(almost.parts.closed, false);
const closing = session();
assert.equal(closing.createPenPath(almost), true);
const openPath = closing.current().document.paths[0];
assert.equal(openPath.closed, false);
const nodeCount = openPath.nodes.length;
assert.equal(closing.closePenPath(openPath.id), true);
const closedPath = closing.current().document.paths[0];
assert.equal(closedPath.closed, true);
assert.equal(closedPath.nodes.length, nodeCount);
assert.equal(closedPath.segments[closedPath.segments.length - 1].to_node, closedPath.nodes[0].id);
assert.equal(closedPath.segments[closedPath.segments.length - 1].from_node, closedPath.nodes[closedPath.nodes.length - 1].id);
assert.notEqual(closedPath.nodes[0].id, closedPath.nodes[closedPath.nodes.length - 1].id);
const moved = closedPath.nodes[1];
assert.equal(closing.moveNode(closedPath.id, moved.id, moved.x_mm + 3, moved.y_mm), true);
assert.equal(closing.current().document.paths[0].closed, true);
assert.equal(closing.current().document.paths[0].segments.at(-1).to_node, closing.current().document.paths[0].nodes[0].id);

const rejected = session();
const beforeReject = JSON.stringify(rejected.current().document);
assert.equal(rejected.createPenPath(sharp, { maxNodes: 2 }), false);
assert.equal(rejected.createPenPath(straight, { maxBytes: 20 }), false);
assert.equal(rejected.createPenPath(straight, { maxPaths: 0 }), false);
assert.equal(JSON.stringify(rejected.current().document), beforeReject);
assert.equal(rejected.current().messageKey, "This stroke has too many points to store. The existing drawing was kept.");

const savedDrawing = session();
assert.equal(savedDrawing.createPenPath(curve), true);
assert.equal(savedDrawing.createPenPath(straight), true);
const saved = JSON.parse(JSON.stringify(savedDrawing.current().document));
assert.equal(savedDrawing.applySave("piece:special", { ok: false, code: "save_failed" }), false);
assert.equal(savedDrawing.current().document.paths.length, 2);
const reopened = Model.createSession();
reopened.activate({ pieceInstanceId: "piece:special", widthMm: 600, lengthMm: 2100 });
const ticket = reopened.beginLoad();
assert.equal(reopened.applyLoaded(ticket.pieceInstanceId, ticket.token, {
    ok: true,
    drawing: saved,
    drawing_version: 3,
}), true);
assert.equal(reopened.current().document.paths.length, 2);
assert.equal(reopened.current().document.paths[0].segments[0].kind, "bezier");
assert.equal(reopened.current().document.paths[1].nodes[1].x_mm, 100);

const frame = Space.pieceFrame({
    sheet_no: 1,
    rotation_deg: 90,
    placement_cm: { x: 0, y: 0 },
    entry_pivot_mm: { x: 0, y: 0 },
    pivot_mm: { x: 0, y: 0 },
}, { 1: { origin_x_mm: 0, origin_y_mm: 0 } }, { widthMm: 600 });
const localNode = straight.parts.nodes[1];
const worldNode = Space.doorToWorld(frame, localNode.x_mm, localNode.y_mm);
assert.equal(localNode.x_mm, 100);
assert.ok(Math.abs(worldNode.x - localNode.x_mm) > 1 || Math.abs(worldNode.y - localNode.y_mm) > 1);
assert.deepEqual(stroke(linePoints(30), "low", { scale: 4 }).parts.nodes, stroke(linePoints(30), "low", { scale: 0.2 }).parts.nodes);

const board = load([
    "public/js/board_editor/history.js",
    "public/js/board_editor/session_document.js",
    "public/js/board_editor/move_geometry.js",
    "public/js/board_editor/rotation_geometry.js",
    "public/js/board_editor/store.js",
]).AlmdinaBoardEditor;
const store = board.createStore({ projection: { pieces: [] } });
store.attachSession({ pieces: { special: { piece_key: "special" } }, boards: {} }, board.History.create({ pieces: {}, boards: {} }));
const fingerprint = JSON.stringify(store.snapshot().session);
pen.createPenPath(straight);
assert.equal(JSON.stringify(store.snapshot().session), fingerprint);
assert.equal(store.snapshot().canUndo, false);

const dom = load([
    "public/js/board_editor/drawing_space.js",
    "public/js/board_editor/editor_mode.js",
    "public/js/board_editor/canvas_renderer.js",
], {
    frappe: { utils: { escape_html: (value) => String(value == null ? "" : value) }, boot: { lang: "ar" } },
    document: null,
});
const helperSource = fs.readFileSync(path.join(root, "tests/js/board_editor_polyline_input.test.js"), "utf8");
vm.runInContext(
    `${helperSource.slice(helperSource.indexOf("const VOID"), helperSource.indexOf("function loadEditor"))}\nthis.MiniElement = MiniElement;\nthis.emit = emit;\n`,
    dom
);
dom.document = {
    createElementNS(_ns, tag) { return new dom.MiniElement(tag, {}, dom.document); },
};
const host = new dom.MiniElement("section", { class: "abe-canvas-host" }, dom.document);
host.clientWidth = 900;
host.clientHeight = 640;
host.getBoundingClientRect = () => ({ left: 0, top: 0, width: 900, height: 640, right: 900, bottom: 640 });
let hostEvents = 0;
host.addEventListener("pointerdown", () => { hostEvents += 1; });
let drawingClicks = 0;
let pans = 0;
let smoothing = "";
let panArmed = false;
const view = {
    editorMode: "drawing",
    canSaveLayout: true,
    drawingTarget: { status: "special", canEdit: true, label: "Special door", widthCm: 60, lengthCm: 210 },
    drawingView: {
        tool: "pen",
        ready: true,
        pen: { smoothing: "low", canClose: false },
        paths: [],
        shapes: [],
    },
    viewport: { scale: 1, opened: true, userAdjusted: true },
    session: { pieces: {}, boards: {} },
    selectedPieceKeys: [],
    projection: { pieces: [], sheets: [], elements: [] },
};
dom.AlmdinaBoardEditor.CanvasRenderer.render(host, view, {
    drawingPointerDown() { drawingClicks += 1; return true; },
    onPanIntent() { pans += 1; },
    isPanKey() { return panArmed; },
    setPenSmoothing(level) { smoothing = level; },
});
assert.equal(host.querySelector('[data-abe-drawing-tool="pen"]').getAttribute("aria-pressed"), "true");
assert.equal(host.querySelectorAll("button[data-abe-drawing-tool='reference_image'], button[data-abe-drawing-tool=\"reference_image\"]").length, 0);
assert.match(host.innerHTML, /is-pen/);
assert.equal(host.querySelector('[data-abe-pen-smoothing="low"]').getAttribute("aria-pressed"), "true");
assert.equal(host.querySelector("[data-abe-drawing-cursor]"), null);
assert.equal(host.querySelector("[data-abe-drawing-length]"), null);
assert.equal(host.querySelector('[data-abe-drawing-action="close-pen"]').disabled, true);
dom.emit(host.querySelector('[data-abe-pen-smoothing="high"]'), "click");
assert.equal(smoothing, "high");
dom.emit(host.querySelector("[data-abe-pen-settings]"), "pointerdown", { button: 0 });
assert.equal(hostEvents, 0);
assert.equal(drawingClicks, 0);
const stage = host.querySelector("[data-abe-stage]");
dom.emit(stage, "pointerdown", { button: 0 });
assert.equal(drawingClicks, 1);
assert.equal(pans, 0);
panArmed = true;
dom.emit(stage, "pointerdown", { button: 0 });
assert.equal(drawingClicks, 1);
assert.equal(pans, 1);
view.drawingView.paths = [{
    id: "p1",
    closed: false,
    selected: true,
    points: [{ id: "n1", x: 10, y: 20 }, { id: "n2", x: 90, y: 20 }],
    markup: "M10 20 L90 20",
}];
dom.AlmdinaBoardEditor.CanvasRenderer.render(host, view, {});
assert.match(host.querySelector("[data-abe-drawing-path]").getAttribute("d"), /M10 20 L90 20/);

const placed = dom.AlmdinaBoardEditor.CanvasRenderer.computePolylineHudPosition({
    startX: 120, startY: 200, endX: 420, endY: 200, width: 160, height: 28, boundsWidth: 900, boundsHeight: 640,
});
const movedHud = dom.AlmdinaBoardEditor.CanvasRenderer.computePolylineHudPosition({
    startX: 120, startY: 200, endX: 620, endY: 260, width: 160, height: 28, boundsWidth: 900, boundsHeight: 640,
});
assert.equal(movedHud.left, placed.left);
assert.equal(movedHud.top, placed.top);

const controller = fs.readFileSync(path.join(root, "public/js/board_editor/controller.js"), "utf8");
const renderer = fs.readFileSync(path.join(root, "public/js/board_editor/canvas_renderer.js"), "utf8");
assert.match(controller, /createPenPath/);
assert.match(controller, /closePenPath/);
assert.match(controller, /releasePointerCapture/);
assert.match(controller, /cancelPenStroke/);
assert.match(controller, /patchPenPreview/);
assert.doesNotMatch(controller, /special_shape_geometry_json|layout_json|snapshot_json/);
const pieceHandler = renderer.slice(renderer.indexOf('querySelectorAll("[data-piece-id]'), renderer.indexOf('querySelectorAll("[data-board-drag]'));
assert.ok(pieceHandler.indexOf("drawingPointerDown") < pieceHandler.indexOf("beginPieceGesture"));
const rotateHandler = renderer.slice(renderer.indexOf('querySelectorAll("[data-abe-rotate-handle]'), renderer.indexOf('querySelectorAll("[data-abe-angle-mirror]'));
assert.ok(rotateHandler.indexOf("drawingPointerDown") < rotateHandler.indexOf("beginRotateGesture"));

console.log("board editor pen tests ok");
