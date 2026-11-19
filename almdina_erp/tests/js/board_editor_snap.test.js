"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.resolve(__dirname, "../..");

function load(files, extras) {
    const context = Object.assign({
        console,
        __: (message) => message,
        frappe: { utils: { escape_html: (value) => String(value == null ? "" : value) }, boot: { lang: "en" } },
        document: { createElementNS() { return { setAttribute() {}, appendChild() {} }; } },
    }, extras || {});
    context.window = context;
    context.globalThis = context;
    vm.createContext(context);
    files.forEach((relative) => {
        vm.runInContext(fs.readFileSync(path.join(root, relative), "utf8"), context, { filename: relative });
    });
    return context;
}

const editor = load([
    "public/js/board_editor/history.js",
    "public/js/board_editor/session_document.js",
    "public/js/board_editor/editor_mode.js",
    "public/js/board_editor/drawing_space.js",
    "public/js/board_editor/drawing_model.js",
    "public/js/board_editor/drawing_snap.js",
    "public/js/board_editor/snap_geometry.js",
    "public/js/board_editor/store.js",
]).AlmdinaBoardEditor;
const Space = editor.DrawingSpace;
const Model = editor.DrawingModel;
const Snap = editor.DrawingSnap;

function line(id, x1, y1, x2, y2) {
    return {
        id,
        closed: false,
        nodes: [
            { id: `${id}a`, x_mm: x1, y_mm: y1 },
            { id: `${id}b`, x_mm: x2, y_mm: y2 },
        ],
        segments: [{ id: `${id}s`, kind: "line", from_node: `${id}a`, to_node: `${id}b` }],
    };
}

function settings(overrides) {
    return Object.assign(Snap.defaultSettings(), overrides || {});
}

function only(types) {
    return settings({
        endpoint: types.includes("endpoint"),
        midpoint: types.includes("midpoint"),
        intersection: types.includes("intersection"),
        alignment: types.includes("alignment"),
        grid: types.includes("grid"),
    });
}

function samePoint(actual, x, y) {
    assert.equal(actual.x, x);
    assert.equal(actual.y, y);
}

function hit(document, pointer, extra) {
    const spec = Object.assign({
        index: Snap.buildIndex(document),
        pointer,
        settings: Snap.defaultSettings(),
        scale: 1,
    }, extra || {});
    return Snap.resolve(spec);
}

function frameFor(rotation, flipH, flipV) {
    return Space.pieceFrame({
        placement_cm: { x: 10, y: 20, w: 60, h: 210, rotated: false },
        entry_pivot_mm: { x: 400, y: 1250 },
        pivot_mm: { x: 400, y: 1250 },
        rotation_deg: rotation,
        flip_h: flipH,
        flip_v: flipV,
        sheet_no: 1,
    }, { 1: { origin_x_mm: 500, origin_y_mm: 40, trim_x_mm: 0, trim_y_mm: 0 } }, {
        widthMm: 600,
        lengthMm: 2100,
    });
}

const cross = {
    paths: [line("h", 0, 100, 400, 100), line("v", 200, 0, 200, 300)],
    shapes: [],
};
const crossing = hit(cross, { x: 202, y: 98 }, { settings: only(["intersection"]) });
assert.equal(crossing.snap.type, "intersection");
samePoint(crossing.point, 200, 100);
assert.ok(crossing.snap.distancePx < 8);
assert.equal(crossing.snap.sourceId.includes("h") && crossing.snap.sourceId.includes("v"), true);

const end = hit({ paths: [line("e", 0, 0, 80, 0)], shapes: [] }, { x: 3, y: 1 });
assert.equal(end.snap.type, "endpoint");
samePoint(end.point, 0, 0);
assert.equal(end.snap.labelKey, "Endpoint");

const middle = hit({ paths: [line("m", 0, 0, 400, 0)], shapes: [] }, { x: 203, y: 2 }, { settings: only(["midpoint"]) });
assert.equal(middle.snap.type, "midpoint");
samePoint(middle.point, 200, 0);

const outside = hit({
    paths: [line("a", 0, 0, 100, 0), line("b", 200, 0, 200, 100)],
    shapes: [],
}, { x: 198, y: 2 }, { settings: only(["intersection"]) });
assert.equal(outside.snap, null);

const parallel = hit({
    paths: [line("p", 0, 0, 400, 0), line("q", 0, 30, 400, 30)],
    shapes: [],
}, { x: 200, y: 15 }, { settings: only(["intersection"]) });
assert.equal(parallel.snap, null);

const overlap = hit({
    paths: [line("o", 0, 0, 100, 0), line("r", 50, 0, 150, 0)],
    shapes: [],
}, { x: 75, y: 1 }, { settings: only(["intersection"]) });
assert.equal(overlap.snap, null);

const joined = hit({
    paths: [line("h", 0, 100, 400, 100), line("v", 200, 0, 200, 100)],
    shapes: [],
}, { x: 200, y: 101 });
assert.equal(joined.snap.type, "endpoint");
samePoint(joined.point, 200, 100);

const rectangle = hit({
    paths: [],
    shapes: [{
        id: "rect",
        kind: "rectangle",
        exploded: false,
        params: { x_mm: 0, y_mm: 0, width_mm: 500, height_mm: 200, rotation_deg: 0 },
    }],
}, { x: 497, y: 2 }, { settings: only(["endpoint"]) });
samePoint(rectangle.point, 500, 0);
assert.equal(rectangle.snap.sourceId.includes("rect"), true);

const ell = hit({
    paths: [],
    shapes: [{
        id: "ell",
        kind: "l_shape",
        exploded: false,
        params: { x_mm: 0, y_mm: 0, width_mm: 300, height_mm: 220, notch_width_mm: 90, notch_height_mm: 70 },
    }],
}, { x: 212, y: 72 }, { settings: only(["endpoint"]) });
samePoint(ell.point, 210, 70);

const arcDoc = {
    paths: [{
        id: "arc",
        closed: false,
        nodes: [{ id: "as", x_mm: 10, y_mm: 0 }, { id: "ae", x_mm: -10, y_mm: 0 }],
        segments: [{ id: "aseg", kind: "arc", from_node: "as", to_node: "ae", radius_mm: 10, large_arc: false, sweep_clockwise: true }],
    }],
    shapes: [],
};
const arcMid = hit(arcDoc, { x: 1, y: 9 }, { settings: only(["midpoint"]) });
samePoint(arcMid.point, 0, 10);

const curve = {
    paths: [{
        id: "curve",
        closed: false,
        nodes: [{ id: "ca", x_mm: 0, y_mm: 0 }, { id: "cb", x_mm: 100, y_mm: 0 }],
        segments: [{
            id: "cs",
            kind: "bezier",
            from_node: "ca",
            to_node: "cb",
            controls: [{ x_mm: 0, y_mm: 0 }, { x_mm: 300, y_mm: 80 }],
        }],
    }],
    shapes: [],
};
const curveIndex = Snap.buildIndex(curve);
const lengthMid = Snap.bezierLengthPoint(curveIndex.beziers[0]);
const parameterMid = {
    x: (0.125 * 0) + (3 * 0.25 * 0.5 * 0) + (3 * 0.5 * 0.25 * 300) + (0.125 * 100),
    y: (0.125 * 0) + (3 * 0.25 * 0.5 * 0) + (3 * 0.5 * 0.25 * 80) + (0.125 * 0),
};
assert.ok(Math.hypot(lengthMid.x - parameterMid.x, lengthMid.y - parameterMid.y) > 1);
const curveHit = hit(curve, lengthMid, { settings: only(["midpoint"]) });
assert.equal(curveHit.snap.type, "midpoint");
assert.ok(Math.hypot(curveHit.point.x - lengthMid.x, curveHit.point.y - lengthMid.y) < 0.01);

const circleCross = hit({
    paths: [line("through", 0, 100, 200, 100)],
    shapes: [{ id: "round", kind: "circle", exploded: false, params: { cx_mm: 100, cy_mm: 100, radius_mm: 50 } }],
}, { x: 52, y: 102 }, { settings: only(["intersection"]) });
samePoint(circleCross.point, 50, 100);

const ellipseMiss = hit({
    paths: [line("side", 10, -100, 10, 100)],
    shapes: [{ id: "oval", kind: "ellipse", exploded: false, params: { cx_mm: 0, cy_mm: 0, rx_mm: 50, ry_mm: 20, rotation_deg: 0 } }],
}, { x: 10, y: 19 }, { settings: only(["intersection"]) });
assert.equal(ellipseMiss.snap, null);

const gridTen = hit({ paths: [], shapes: [] }, { x: 14, y: 6 }, { settings: settings({ grid: true, spacing: 10, endpoint: false, midpoint: false, intersection: false, alignment: false }) });
samePoint(gridTen.point, 10, 10);
const gridFive = hit({ paths: [], shapes: [] }, { x: 14, y: 6 }, { settings: settings({ grid: true, spacing: 5, endpoint: false, midpoint: false, intersection: false, alignment: false }) });
samePoint(gridFive.point, 15, 5);
assert.equal(Snap.normalizeSettings({ spacing: 7 }).spacing, 10);
assert.equal(Snap.defaultSettings().grid, false);

const nearZoom = hit({ paths: [line("z", 0, 0, 40, 0)], shapes: [] }, { x: 6, y: 0 }, { scale: 1 });
const farZoom = hit({ paths: [line("z", 0, 0, 40, 0)], shapes: [] }, { x: 6, y: 0 }, { scale: 2 });
samePoint(nearZoom.point, 0, 0);
assert.equal(farZoom.snap, null);
assert.equal(Snap.thresholdMm(1), 8);
assert.equal(Snap.thresholdMm(2), 4);

[30, 90].forEach((rotation) => {
    const frame = frameFor(rotation, false, false);
    const back = Space.worldToDoor(frame, Space.doorToWorld(frame, 6, 0).x, Space.doorToWorld(frame, 6, 0).y);
    const snapped = hit({ paths: [line("rot", 0, 0, 40, 0)], shapes: [] }, back, { scale: 1 });
    samePoint(snapped.point, 0, 0);
    const displayed = Space.doorToWorld(frame, snapped.point.x, snapped.point.y);
    const exact = Space.doorToWorld(frame, 0, 0);
    assert.ok(Math.abs(displayed.x - exact.x) < 0.001);
    assert.ok(Math.abs(displayed.y - exact.y) < 0.001);
});
const flipped = frameFor(0, true, true);
const flippedBack = Space.worldToDoor(flipped, Space.doorToWorld(flipped, 6, 0).x, Space.doorToWorld(flipped, 6, 0).y);
samePoint(hit({ paths: [line("flip", 0, 0, 40, 0)], shapes: [] }, flippedBack).point, 0, 0);

assert.equal(hit({ paths: [line("far", 0, 0, 20, 0)], shapes: [] }, { x: 40, y: 40 }).snap, null);

const first = hit({ paths: [line("pair", 0, 0, 3, 0)], shapes: [] }, { x: 1, y: 0 });
const held = hit({ paths: [line("pair", 0, 0, 3, 0)], shapes: [] }, { x: 2, y: 0 }, { hold: first.snap });
samePoint(first.point, 0, 0);
samePoint(held.point, 0, 0);
assert.equal(hit({ paths: [line("pair", 0, 0, 3, 0)], shapes: [] }, { x: 30, y: 0 }, { hold: first.snap }).snap, null);

const priority = Snap.PRIORITY;
assert.equal(priority.endpoint, 1);
assert.equal(priority.intersection, 2);
assert.equal(priority.midpoint, 3);
assert.equal(priority.alignment, 4);
assert.equal(priority.grid, 5);
const tied = hit({
    paths: [line("h", 0, 100, 400, 100), line("v", 200, 0, 200, 100)],
    shapes: [],
}, { x: 200, y: 100 });
assert.equal(tied.snap.type, "endpoint");

const noMid = hit({ paths: [line("m", 0, 0, 400, 0)], shapes: [] }, { x: 200, y: 1 }, { settings: settings({ midpoint: false }) });
assert.notEqual(noMid.snap && noMid.snap.type, "midpoint");
assert.equal(hit({ paths: [line("m", 0, 0, 400, 0)], shapes: [] }, { x: 200, y: 1 }, { settings: settings({ midpoint: true, endpoint: false, intersection: false }) }).snap.type, "midpoint");

const bypass = hit({ paths: [line("e", 0, 0, 80, 0)], shapes: [] }, { x: 1, y: 1 }, { alt: true });
assert.equal(bypass.snap, null);
samePoint(bypass.point, 1, 1);

const shifted = hit({ paths: [], shapes: [] }, { x: 100, y: 40 }, { anchor: { x: 0, y: 0 }, shift: true });
assert.equal(shifted.angle, 15);
assert.equal(shifted.snap, null);
const onRay = hit({ paths: [line("ray", 100, 0, 140, 0)], shapes: [] }, { x: 96, y: 1 }, { anchor: { x: 0, y: 0 }, shift: true, settings: only(["endpoint"]) });
assert.equal(onRay.snap.type, "endpoint");
samePoint(onRay.point, 100, 0);

const drawing = Model.createSession();
drawing.activate({ pieceInstanceId: "piece:special", widthMm: 800, lengthMm: 2100 });
drawing.markReady();
const beforeMoves = drawing.current().past.length;
for (let step = 0; step < 12; step += 1) hit(cross, { x: 200 + (step * 0.1), y: 100 });
assert.equal(drawing.current().past.length, beforeMoves);
const jsonBefore = JSON.stringify(drawing.current().document);
hit(cross, { x: 3, y: 1 });
assert.equal(JSON.stringify(drawing.current().document), jsonBefore);

const start = hit({ paths: [line("seed", 10, 20, 80, 20)], shapes: [] }, { x: 12, y: 21 }, { settings: only(["endpoint"]) });
drawing.placePoint(start.point.x, start.point.y);
const finish = hit(cross, { x: 201, y: 99 }, { settings: only(["intersection"]) });
drawing.placePoint(finish.point.x, finish.point.y);
const drawn = drawing.current().document.paths[0];
samePoint({ x: drawn.nodes[0].x_mm, y: drawn.nodes[0].y_mm }, 10, 20);
samePoint({ x: drawn.nodes[1].x_mm, y: drawn.nodes[1].y_mm }, 200, 100);
assert.notEqual(drawn.nodes[0].id, "seeda");
assert.equal(drawing.current().past.length, beforeMoves + 2);

drawing.finish();
drawing.placePoint(0, 0);
drawing.placePoint(120, 0);
const active = drawing.current();
const closing = hit(active.document, { x: 2, y: 1 }, {
    settings: only(["endpoint"]),
    exclude: { pathId: active.cursor.pathId, nodeId: active.cursor.nodeId },
});
assert.equal(closing.snap.closes, true);
assert.equal(drawing.close(), true);
const closed = drawing.current().document.paths[drawing.current().document.paths.length - 1];
assert.equal(closed.closed, true);
assert.equal(closed.nodes.length, 2);
assert.equal(closed.segments[closed.segments.length - 1].to_node, closed.nodes[0].id);

const nodeDrawing = Model.createSession();
nodeDrawing.activate({ pieceInstanceId: "piece:special", widthMm: 800, lengthMm: 2100 });
nodeDrawing.markReady();
nodeDrawing.placePoint(0, 0);
nodeDrawing.placePoint(50, 0);
nodeDrawing.finish();
nodeDrawing.placePoint(400, 10);
nodeDrawing.placePoint(400, 80);
nodeDrawing.finish();
const paths = nodeDrawing.current().document.paths;
const dragged = paths[1].nodes[0];
const target = hit(nodeDrawing.current().document, { x: 2, y: 1 }, {
    settings: only(["endpoint"]),
    exclude: { pathId: paths[1].id, nodeId: dragged.id },
});
samePoint(target.point, 0, 0);
const pastBeforeMove = nodeDrawing.current().past.length;
assert.equal(nodeDrawing.moveNode(paths[1].id, dragged.id, target.point.x, target.point.y, { history: true }), true);
assert.equal(nodeDrawing.current().document.paths[1].nodes[0].x_mm, 0);
assert.equal(nodeDrawing.current().document.paths[1].nodes[0].id, dragged.id);
assert.notEqual(nodeDrawing.current().document.paths[1].nodes[0].id, paths[0].nodes[0].id);
assert.equal(nodeDrawing.current().past.length, pastBeforeMove + 1);
const self = hit(nodeDrawing.current().document, { x: 400, y: 80 }, {
    settings: only(["endpoint"]),
    exclude: { pathId: paths[1].id, nodeId: paths[1].nodes[1].id },
    blockPoints: [{ x: 0, y: 0 }],
});
assert.equal(self.snap, null);
const blocked = nodeDrawing.current().past.length;
assert.equal(nodeDrawing.moveNode(paths[1].id, paths[1].nodes[1].id, 0, 0), false);
assert.equal(nodeDrawing.current().past.length, blocked);

const numeric = Model.createSession();
numeric.activate({ pieceInstanceId: "piece:special", widthMm: 800, lengthMm: 2100 });
numeric.markReady();
numeric.placePoint(100, 100);
const typed = numeric.commitNumeric({ lengthText: "200", angleText: "90", previewLength: 40, previewAngle: 10 });
assert.equal(typed.ok, true);
assert.equal(numeric.current().document.paths[0].nodes[1].x_mm, 100);
assert.equal(numeric.current().document.paths[0].nodes[1].y_mm, 300);

const gesture = Space.createPenGesture("off");
assert.equal(gesture.pointerDown({ pointerId: 1, x: 1.2, y: 1.4 }), true);
assert.equal(gesture.pointerMove({ pointerId: 1, x: 8.2, y: 1.5 }), true);
assert.equal(gesture.pointerMove({ pointerId: 1, x: 16.4, y: 1.3 }), true);
const ink = gesture.pointerUp({ pointerId: 1, x: 24.6, y: 1.4 });
assert.equal(ink.ok, true);
ink.parts.nodes.forEach((node) => {
    assert.ok(Math.abs(node.y_mm) > 0.5);
});

const layout = editor.SessionDocument.buildFromProjection({
    pieces: [{
        piece_id: 1,
        piece_instance_id: "piece:a",
        piece_type: "Special",
        label: "Door",
        sheet_no: 1,
        x: 10,
        y: 20,
        w: 60,
        h: 210,
        original_w: 60,
        original_h: 210,
        editable: true,
    }],
    sheets: [{ sheet_no: 1, origin_x_mm: 500, origin_y_mm: 40 }],
});
const store = editor.createStore({ projection: { pieces: [], sheets: [] } });
store.attachSession(layout, editor.History.create(layout));
store.noteDraftBaseline({
    canSaveLayout: true,
    draftVersion: 1,
    savedFingerprint: editor.SessionDocument.distributionFingerprint(layout),
});
const fingerprint = editor.SessionDocument.distributionFingerprint(store.snapshot().session);
store.setDrawingView({ snapSettings: Snap.defaultSettings(), snapMenuOpen: true });
assert.equal(editor.SessionDocument.distributionFingerprint(store.snapshot().session), fingerprint);
assert.equal(store.snapshot().distributionDirty, false);
assert.equal(store.snapshot().canUndo, false);

assert.equal(typeof editor.SnapGeometry.suggestPieceSnap, "function");
assert.equal(editor.SnapGeometry.SNAP_ENTER_PX, 8);
const snapSource = fs.readFileSync(path.join(root, "public/js/board_editor/drawing_snap.js"), "utf8");
const magnetSource = fs.readFileSync(path.join(root, "public/js/board_editor/snap_geometry.js"), "utf8");
const controllerSource = fs.readFileSync(path.join(root, "public/js/board_editor/controller.js"), "utf8");
assert.doesNotMatch(snapSource, /suggestPieceSnap|magnetEnabled|distributionFingerprint|special_shape_geometry_json|snapshot_json|layout_json/);
assert.doesNotMatch(magnetSource, /DrawingSnap/);
assert.match(snapSource, /\.slice\(0,\s*48\)/);
assert.match(controllerSource, /penGesture\.pointerMove\(\{ pointerId: event\.pointerId, x: mapped\.door\.x, y: mapped\.door\.y \}\)/);
assert.match(controllerSource, /function beginPenStroke[\s\S]{0,700}resolveSmartPoint/);
assert.match(controllerSource, /function finishPenStroke[\s\S]{0,700}resolveSmartPoint/);
assert.match(controllerSource, /drawingPointer\.snap = null;\s*snapOverlay = null/);
assert.match(controllerSource, /commitNumeric\(/);
assert.doesNotMatch(controllerSource, /setDrawingTool\("snap"\)/);
assert.match(controllerSource, /alt: event\.altKey === true/);
assert.match(controllerSource, /exclude: \{ pathId: gesture\.pathId, nodeId: gesture\.nodeId \}/);

const nodes = [];
const segments = [];
for (let index = 0; index < 3000; index += 1) {
    nodes.push({ id: `n${index}`, x_mm: index, y_mm: (index % 2) * 40 });
    if (index) segments.push({ id: `s${index}`, kind: "line", from_node: `n${index - 1}`, to_node: `n${index}` });
}
const started = Date.now();
const crowded = Snap.buildIndex({ paths: [{ id: "crowd", closed: false, nodes, segments }], shapes: [] });
const crowdedHit = Snap.resolve({ index: crowded, pointer: { x: 10.4, y: 0.2 }, settings: Snap.defaultSettings(), scale: 1 });
assert.ok(Date.now() - started < 1500);
assert.equal(crowdedHit.snap.type, "endpoint");
samePoint(crowdedHit.point, 10, 0);

const helperSource = fs.readFileSync(path.join(root, "tests/js/board_editor_polyline_input.test.js"), "utf8");
const dom = load([
    "public/js/board_editor/editor_mode.js",
    "public/js/board_editor/canvas_renderer.js",
    "public/js/board_editor/drawing_properties_panel.js",
], {
    frappe: { utils: { escape_html: (value) => String(value == null ? "" : value) }, boot: { lang: "en" } },
    document: null,
});
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
let drawingClicks = 0;
let tool = "";
let snapToggle = 0;
let snapOption = null;
host.addEventListener("pointerdown", () => { hostEvents += 1; });
const view = {
    editorMode: "drawing",
    canSaveLayout: true,
    drawingTarget: { status: "special", canEdit: true, label: "Special door", widthCm: 60, lengthCm: 210 },
    drawingView: {
        tool: "polyline",
        ready: true,
        snapMenuOpen: true,
        snapSettings: Snap.defaultSettings(),
        measure: { mode: "draw", enabled: true, lengthMm: 80, angleDeg: 0 },
        snap: { x: 300, y: 180, type: "endpoint", labelKey: "Endpoint" },
        paths: [{ id: "p", closed: false, selected: true, active: true, points: [{ id: "n", x: 100, y: 180 }, { id: "m", x: 300, y: 180 }] }],
        shapes: [],
    },
    viewport: { scale: 1, opened: true, userAdjusted: true },
    session: { pieces: {}, boards: {} },
    selectedPieceKeys: [],
    projection: { pieces: [], sheets: [], elements: [] },
};
const snapHandlers = {
    setDrawingTool(next) { tool = next; },
    drawingPointerDown() { drawingClicks += 1; return true; },
    toggleSnapMenu() { snapToggle += 1; },
    setSnapOption(name, value) { snapOption = [name, value]; },
};
dom.AlmdinaBoardEditor.CanvasRenderer.render(host, view, snapHandlers);
const properties = new dom.MiniElement("aside", {}, dom.document);
dom.AlmdinaBoardEditor.DrawingProperties.render(properties, view, snapHandlers);
const marker = host.querySelector('[data-abe-snap-type="endpoint"]');
assert.ok(marker);
assert.equal(marker.getAttribute("pointer-events"), "none");
assert.equal(marker.getAttribute("data-abe-drawing-snap"), "1");
assert.equal(host.querySelector("[data-abe-snap-label]").getAttribute("pointer-events"), "none");
assert.equal(host.querySelector("[data-abe-snap-label]").getAttribute("data-abe-snap-label"), "Endpoint");
const labelY = Number(host.querySelector("[data-abe-snap-label]").getAttribute("y"));
assert.ok(labelY > 180);
const button = host.querySelector("[data-abe-snap-toggle]");
assert.equal(button.getAttribute("aria-pressed"), "true");
assert.equal(button.getAttribute("data-abe-drawing-tool"), null);
const menu = properties.querySelector("[data-abe-snap-menu]");
assert.ok(menu);
assert.equal(menu.querySelector('[data-abe-snap-option="endpoint"]').getAttribute("checked") != null, true);
assert.equal(menu.querySelector('[data-abe-snap-option="grid"]').getAttribute("checked"), null);
assert.equal(menu.querySelector('[data-abe-snap-spacing="1"]').querySelector('[value="10"]').getAttribute("selected") != null, true);
assert.ok(host.querySelector("[data-abe-drawing-length]"));
assert.ok(host.querySelector("[data-abe-drawing-angle]"));
dom.emit(button, "click");
assert.equal(snapToggle, 1);
assert.equal(tool, "");
dom.emit(menu, "pointerdown", { button: 0 });
assert.equal(hostEvents, 0);
assert.equal(drawingClicks, 0);
const midpointBox = menu.querySelector('[data-abe-snap-option="midpoint"]');
midpointBox.checked = false;
dom.emit(midpointBox, "change");
assert.equal(snapOption[0], "midpoint");
assert.equal(snapOption[1], false);
const hud = dom.AlmdinaBoardEditor.CanvasRenderer.computePolylineHudPosition({
    startX: 100, startY: 180, endX: 300, endY: 180, width: 160, height: 28, boundsWidth: 900, boundsHeight: 640,
});
const hudLater = dom.AlmdinaBoardEditor.CanvasRenderer.computePolylineHudPosition({
    startX: 100, startY: 180, endX: 360, endY: 190, width: 160, height: 28, boundsWidth: 900, boundsHeight: 640, previousSide: hud.side,
});
assert.equal(hud.left, hudLater.left);
assert.equal(hud.top, hudLater.top);
assert.ok(labelY > hud.top + 28);

const world = host.querySelector(".abe-world");
const pathCount = world.querySelectorAll("[data-abe-drawing-path]").length;
host.__abeWorldMetrics = { scale: 2 };
dom.AlmdinaBoardEditor.CanvasRenderer.patchDrawingPreview(host, {
    x1: 100, y1: 180, x2: 300, y2: 180,
}, { x: 300, y: 180, type: "intersection", labelKey: "Intersection" }, null);
assert.equal(world.querySelectorAll("[data-abe-drawing-path]").length, pathCount);
assert.equal(world.querySelector('[data-abe-snap-type="intersection"]').getAttribute("pointer-events"), "none");
assert.equal(world.querySelector("[data-abe-snap-label]").getAttribute("data-abe-snap-label"), "Intersection");
assert.equal(Number(world.querySelector("[data-abe-snap-label]").getAttribute("x")), 306);

view.drawingTarget.canEdit = false;
view.drawingView.snapMenuOpen = false;
dom.AlmdinaBoardEditor.CanvasRenderer.render(host, view, {});
assert.equal(host.querySelector("[data-abe-snap-toggle]"), null);
assert.match(host.innerHTML, /aria-disabled="true"/);

const catalog = fs.readFileSync(path.join(root, "translations/ar.csv"), "utf8");
["Smart Snap,الالتقاط الذكي", "Endpoint,نهاية", "Midpoint,منتصف", "Intersection,تقاطع", "Grid,شبكة", "Horizontal / Vertical,أفقي / عمودي", "Grid spacing,خطوة الشبكة", "Horizontal,أفقي", "Vertical,عمودي"].forEach((row) => {
    assert.ok(catalog.includes(row), row);
});
const css = fs.readFileSync(path.join(root, "public/css/board_editor.css"), "utf8");
assert.match(css, /\.abe-snap-menu\s*\{[^}]*flex-wrap:\s*wrap/);
assert.doesNotMatch(css, /\.abe-snap-menu\s*\{[^}]*overflow/);
const page = fs.readFileSync(path.join(root, "almdina_erp/page/board_editor/board_editor.js"), "utf8");
assert.match(page, /drawing_snap\.js\?v=1/);
assert.match(page, /canvas_renderer\.js\?v=58/);
assert.match(page, /controller\.js\?v=57/);
assert.match(page, /board_editor\.css\?v=53/);

console.log("board editor snap tests ok");

// Piece magnet and alignment snaps.
(() => {
"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.resolve(__dirname, "../..");

function load() {
    const files = [
        "public/js/board_editor/history.js",
        "public/js/board_editor/session_document.js",
        "public/js/board_editor/move_geometry.js",
        "public/js/board_editor/snap_geometry.js",
        "public/js/board_editor/store.js",
        "public/js/board_editor/move_interaction.js",
        "public/js/board_editor/canvas_renderer.js",
    ];
    const context = {
        frappe: { utils: { escape_html: (value) => String(value) } },
        __: (message) => message,
        document: {
            createElementNS: () => ({
                setAttribute() {},
                style: {},
            }),
        },
    };
    context.window = context;
    context.globalThis = context;
    vm.createContext(context);
    files.forEach((relative) => {
        vm.runInContext(fs.readFileSync(path.join(root, relative), "utf8"), context);
    });
    return context.window.AlmdinaBoardEditor;
}

const editor = load();
const { MoveGeometry, SnapGeometry, createStore, History, createMoveInteraction } = editor;

assert.equal(SnapGeometry.SNAP_ENTER_PX, 8);
assert.equal(SnapGeometry.SNAP_EXIT_PX, 12);
assert.equal(SnapGeometry.thresholdMmFromScale(2, 8), 4);
assert.equal(SnapGeometry.thresholdMmFromScale(0.5, 8), 16);

const session = {
    boards: {
        1: {
            sheet_no: 1,
            origin_x_mm: 0,
            origin_y_mm: 0,
            width_mm: 1000,
            height_mm: 1000,
            trim_x_mm: 10,
            trim_y_mm: 10,
            usable_width_mm: 980,
            usable_length_mm: 980,
            title_band_mm: 36,
        },
    },
    pieces: {
        "instance:a": {
            piece_key: "instance:a",
            piece_id: 1,
            piece_instance_id: "a",
            sheet_no: 1,
            local_x_mm: 100,
            local_y_mm: 100,
            placement_cm: { x: 10, y: 10, w: 20, h: 20 },
            outline_mm: [[100, 100], [300, 100], [300, 300], [100, 300]],
            editable: true,
            glass_host_key: null,
        },
        "instance:b": {
            piece_key: "instance:b",
            piece_id: 2,
            piece_instance_id: "b",
            sheet_no: 1,
            local_x_mm: 500,
            local_y_mm: 100,
            placement_cm: { x: 50, y: 10, w: 20, h: 20 },
            outline_mm: [[500, 100], [700, 100], [700, 300], [500, 300]],
            editable: true,
            glass_host_key: null,
        },
        "instance:hidden": {
            piece_key: "instance:hidden",
            piece_id: 3,
            piece_instance_id: "hidden",
            sheet_no: 1,
            local_x_mm: 100,
            local_y_mm: 500,
            placement_cm: { x: 10, y: 50, w: 20, h: 10 },
            outline_mm: [[100, 500], [300, 500], [300, 600], [100, 600]],
            editable: true,
            glass_host_key: null,
        },
    },
    kerf_mm: 4,
    stale_cut_path_sheets: [],
    stale_unbound_text_sheets: [],
};

// Snap to usable left (world usable x = 10). Current world x = 110.
{
    const suggestion = SnapGeometry.suggestPieceSnap(session, "instance:a", 12, 110, {
        magnetEnabled: true,
        thresholdMm: 12,
    });
    assert.equal(suggestion.ok, true);
    const proposal = MoveGeometry.proposePieceDrop(
        session,
        "instance:a",
        110 + suggestion.dx,
        110 + suggestion.dy
    );
    assert.equal(proposal.ok, true);
    assert.equal(Math.round(proposal.local_x_mm), 0);
    assert.ok(suggestion.guides.length >= 1);
}

// Neighbour snap uses kerf once.
{
    const suggestion = SnapGeometry.suggestPieceSnap(session, "instance:a", 310, 110, {
        magnetEnabled: true,
        thresholdMm: 25,
    });
    assert.equal(suggestion.ok, true);
    const proposal = MoveGeometry.proposePieceDrop(
        session,
        "instance:a",
        110 + suggestion.dx,
        110 + suggestion.dy
    );
    assert.equal(proposal.ok, true);
    assert.equal(Math.round(proposal.local_x_mm + 200 + session.kerf_mm), 500);
}

// Magnet off / Alt path → no snap.
{
    const off = SnapGeometry.suggestPieceSnap(session, "instance:a", 12, 110, {
        magnetEnabled: false,
        thresholdMm: 12,
    });
    assert.equal(off.ok, false);
}

// Hidden piece still participates as a snap/validation target.
{
    const suggestion = SnapGeometry.suggestPieceSnap(session, "instance:a", 110, 400, {
        magnetEnabled: true,
        thresholdMm: 30,
    });
    if (suggestion.ok) {
        const proposal = MoveGeometry.proposePieceDrop(
            session,
            "instance:a",
            110 + suggestion.dx,
            110 + suggestion.dy
        );
        assert.equal(proposal.ok, true);
        // Must clear kerf against the hidden piece when snapping vertically near it.
        const aBottom = proposal.local_y_mm + 200;
        if (Math.abs(proposal.local_x_mm - 100) < 1) {
            assert.ok(aBottom + session.kerf_mm <= 500 + 1e-6 || proposal.local_y_mm >= 600 + session.kerf_mm - 1e-6);
        }
    }
}

// Self-group edges are not snap targets: host+guest moving together.
{
    const hosted = JSON.parse(JSON.stringify(session));
    hosted.pieces["instance:b"].glass_host_key = "instance:a";
    hosted.pieces["instance:b"].local_x_mm = 150;
    hosted.pieces["instance:b"].local_y_mm = 150;
    hosted.pieces["instance:b"].outline_mm = [[150, 150], [250, 150], [250, 250], [150, 250]];
    const ids = MoveGeometry.draggedPieceIds(hosted, "instance:a");
    assert.ok(ids.includes("instance:b"));
    const suggestion = SnapGeometry.suggestPieceSnap(hosted, "instance:a", 160, 160, {
        magnetEnabled: true,
        thresholdMm: 40,
    });
    if (suggestion.ok) {
        assert.notEqual(suggestion.source, "piece:instance:b");
    }
}

// Store magnet flag is session UI state, not History.
{
    const store = createStore({ projection: { sheets: [], pieces: [], layers: [] } });
    assert.equal(store.snapshot().magnetEnabled, true);
    store.toggleMagnet();
    assert.equal(store.snapshot().magnetEnabled, false);
    store.setMagnetEnabled(true);
    assert.equal(store.snapshot().magnetEnabled, true);
}

// Interaction applies snap to the committed delta and clears guides on cancel.
{
    let now = 0;
    const timers = new Map();
    let tid = 1;
    const store = createStore({ projection: { sheets: [], pieces: [], layers: [] } });
    const history = History.create(session);
    store.attachSession(history.get(), history);
    const stage = {
        classList: {
            _set: new Set(),
            toggle(name, on) { if (on) this._set.add(name); else this._set.delete(name); },
            contains(name) { return this._set.has(name); },
            add(name) { this._set.add(name); },
            remove(name) { this._set.delete(name); },
        },
        style: {},
        scrollLeft: 0,
        scrollTop: 0,
        getBoundingClientRect: () => ({ left: 0, top: 0, right: 800, bottom: 600, width: 800, height: 600 }),
    };
    const svg = { getBoundingClientRect: () => ({ left: 0, top: 0, right: 800, bottom: 600, width: 800, height: 600 }) };
    const target = { setPointerCapture() {}, releasePointerCapture() {} };
    let lastPreview = null;
    const interaction = createMoveInteraction({
        store,
        getStageEl: () => stage,
        getSvgEl: () => svg,
        getWorldMetrics: () => ({ minX: 0, minY: 0, width: 800, height: 600, scale: 1 }),
        getScale: () => 1,
        onPreview: (preview) => { lastPreview = preview; },
        isPanKey: () => false,
        isAltKey: () => false,
        now: () => now,
        setTimeout: (fn, ms) => { const id = tid++; timers.set(id, { at: now + ms, fn }); return id; },
        clearTimeout: (id) => timers.delete(id),
    });
    function advance(ms) {
        now += ms;
        [...timers.entries()].filter(([, row]) => row.at <= now).forEach(([id, row]) => {
            timers.delete(id);
            row.fn();
        });
    }
    function pointer(x, y) {
        return {
            button: 0,
            pointerId: 1,
            pointerType: "mouse",
            clientX: x,
            clientY: y,
            currentTarget: target,
            target,
            stopPropagation() {},
            preventDefault() {},
        };
    }

    // World metrics map client→world 1:1 with scale in metrics width/height matching svg.
    // piece world origin for a is (110,110). Start drag there, move near usable left.
    interaction.beginPieceGesture("instance:a", pointer(110, 110), { pieceId: 1 });
    interaction.onPointerMove(pointer(110 + 6, 110));
    interaction.onPointerMove(pointer(20, 110));
    assert.equal(interaction.getPhase(), "dragging");
    assert.ok(lastPreview);
    assert.equal(lastPreview.snapped, true);
    assert.ok((lastPreview.guides || []).length >= 1);
    const snappedDx = lastPreview.dx;
    interaction.onPointerUp(pointer(20, 110));
    assert.equal(history.state().canUndo, true);
    assert.equal(Math.round(store.snapshot().session.pieces["instance:a"].local_x_mm), 0);
    assert.equal(Math.round(snappedDx), Math.round(0 - 100));

    // Undo restores exact pre-snap placement.
    store.undo();
    assert.equal(store.snapshot().session.pieces["instance:a"].local_x_mm, 100);

    // Cancel clears guides.
    interaction.beginPieceGesture("instance:a", pointer(110, 110), { pieceId: 1 });
    interaction.onPointerMove(pointer(116, 110));
    interaction.onPointerMove(pointer(20, 110));
    assert.equal(lastPreview.snapped, true);
    interaction.cancel();
    assert.equal(lastPreview, null);
}

const canvasSource = fs.readFileSync(path.join(root, "public/js/board_editor/canvas_renderer.js"), "utf8");
assert.match(canvasSource, /data-abe-magnet/);
assert.match(canvasSource, /data-abe-guide/);
assert.match(canvasSource, /data-abe-guide-kind/);
assert.match(canvasSource, /isAlignment \? "#d92d20" : "#0b5fff"/);
assert.match(canvasSource, /isAlignment \? "2" : "1\.25"/);
assert.match(canvasSource, /vector-effect/);
assert.doesNotMatch(canvasSource, /abe-tool-select/);

// Smart alignment: top / bottom / left / right / centerX / centerY + guide geometry.
{
    const alignSession = JSON.parse(JSON.stringify(session));
    delete alignSession.pieces["instance:hidden"];
    // Offset B vertically so tops differ by 5mm in world (trim 10 → world tops 110 vs 115).
    alignSession.pieces["instance:b"].local_y_mm = 105;
    alignSession.pieces["instance:b"].outline_mm = [[500, 105], [700, 105], [700, 305], [500, 305]];

    const top = SnapGeometry.suggestPieceSnap(alignSession, "instance:a", 110, 112, {
        magnetEnabled: true,
        thresholdMm: 8,
    });
    assert.equal(top.ok, true);
    assert.match(String(top.source), /^align:top:/);
    assert.equal(Math.round(110 + top.dy), 115);
    assert.ok((top.guides || []).some((guide) => guide.kind === "alignment" && guide.mode === "top"));
    const topGuide = top.guides.find((guide) => guide.kind === "alignment");
    assert.equal(Math.round(topGuide.y1), 115);
    assert.equal(Math.round(topGuide.y2), 115);
    assert.ok(topGuide.x2 > topGuide.x1);
    assert.equal(topGuide.sourcePieceKey, "instance:a");
    assert.equal(topGuide.targetPieceKey, "instance:b");

    // Bottom alignment: taller B so top is outside threshold while bottoms are near.
    alignSession.pieces["instance:b"].local_y_mm = 105;
    alignSession.pieces["instance:b"].outline_mm = [[500, 105], [700, 105], [700, 355], [500, 355]];
    const bottom = SnapGeometry.suggestPieceSnap(alignSession, "instance:a", 110, 162, {
        magnetEnabled: true,
        thresholdMm: 8,
    });
    assert.equal(bottom.ok, true);
    assert.match(String(bottom.source), /align:bottom:/);
    assert.equal(Math.round(110 + bottom.dy + 200), 365);

    // Left alignment with vertically separated neighbour (world left of B = 114).
    alignSession.pieces["instance:b"].local_x_mm = 104;
    alignSession.pieces["instance:b"].local_y_mm = 500;
    alignSession.pieces["instance:b"].outline_mm = [[104, 500], [304, 500], [304, 700], [104, 700]];
    const left = SnapGeometry.suggestPieceSnap(alignSession, "instance:a", 108, 110, {
        magnetEnabled: true,
        thresholdMm: 8,
    });
    assert.equal(left.ok, true);
    assert.match(String(left.source), /align:left:/);
    assert.equal(Math.round(110 + left.dx), 114);
    const leftGuide = left.guides.find((guide) => guide.kind === "alignment");
    assert.equal(leftGuide.mode, "left");
    assert.equal(Math.round(leftGuide.x1), Math.round(leftGuide.x2));

    // Right alignment: wider B so left is outside threshold while rights are near.
    alignSession.pieces["instance:b"].local_x_mm = 496;
    alignSession.pieces["instance:b"].outline_mm = [[496, 500], [746, 500], [746, 700], [496, 700]];
    const right = SnapGeometry.suggestPieceSnap(alignSession, "instance:a", 552, 110, {
        magnetEnabled: true,
        thresholdMm: 8,
    });
    assert.equal(right.ok, true);
    assert.match(String(right.source), /align:right:/);
    assert.equal(Math.round(110 + right.dx + 200), 756);

    // Center X / Center Y: narrower B so edge aligns stay outside the enter threshold.
    alignSession.pieces["instance:b"].local_x_mm = 550;
    alignSession.pieces["instance:b"].local_y_mm = 550;
    alignSession.pieces["instance:b"].outline_mm = [[550, 550], [650, 550], [650, 650], [550, 650]];
    const centerX = SnapGeometry.suggestPieceSnap(alignSession, "instance:a", 506, 110, {
        magnetEnabled: true,
        thresholdMm: 8,
    });
    assert.equal(centerX.ok, true);
    assert.match(String(centerX.source), /align:centerX:/);
    const aCenterX = 110 + centerX.dx + 100;
    assert.equal(Math.round(aCenterX), 610);

    const centerY = SnapGeometry.suggestPieceSnap(alignSession, "instance:a", 110, 506, {
        magnetEnabled: true,
        thresholdMm: 8,
    });
    assert.equal(centerY.ok, true);
    assert.match(String(centerY.source), /align:centerY:/);
    const aCenterY = 110 + centerY.dy + 100;
    assert.equal(Math.round(aCenterY), 610);
}

// Alignment that would overlap must be rejected (free drag remains).
{
    const clash = JSON.parse(JSON.stringify(session));
    // B sits above A; top-align would stack them on the same footprint region.
    clash.pieces["instance:b"].local_x_mm = 100;
    clash.pieces["instance:b"].local_y_mm = 105;
    clash.pieces["instance:b"].outline_mm = [[100, 105], [300, 105], [300, 305], [100, 305]];
    const suggestion = SnapGeometry.suggestPieceSnap(clash, "instance:a", 110, 112, {
        magnetEnabled: true,
        thresholdMm: 8,
    });
    if (suggestion.ok) {
        assert.doesNotMatch(String(suggestion.source), /align:top:/);
    }
}

// Combined kerf (X) + top alignment (Y).
{
    const combo = JSON.parse(JSON.stringify(session));
    combo.pieces["instance:b"].local_y_mm = 105;
    combo.pieces["instance:b"].outline_mm = [[500, 105], [700, 105], [700, 305], [500, 305]];
    // Approach from a near-kerf X and near-top Y.
    const suggestion = SnapGeometry.suggestPieceSnap(combo, "instance:a", 304, 112, {
        magnetEnabled: true,
        thresholdMm: 8,
    });
    assert.equal(suggestion.ok, true);
    const proposal = MoveGeometry.proposePieceDrop(
        combo,
        "instance:a",
        110 + suggestion.dx,
        110 + suggestion.dy
    );
    assert.equal(proposal.ok, true);
    assert.equal(Math.round(proposal.local_x_mm + 200 + combo.kerf_mm), 500);
    assert.equal(Math.round(proposal.local_y_mm), 105);
    assert.ok((suggestion.guides || []).length >= 1);
}

// Off-board pieces can still align visually without jumping onto a board.
{
    const floating = JSON.parse(JSON.stringify(session));
    floating.pieces["instance:a"].sheet_no = null;
    floating.pieces["instance:a"].local_x_mm = 2000;
    floating.pieces["instance:a"].local_y_mm = 100;
    floating.pieces["instance:a"].outline_mm = [[2000, 100], [2200, 100], [2200, 300], [2000, 300]];
    floating.pieces["instance:b"].sheet_no = null;
    floating.pieces["instance:b"].local_x_mm = 2400;
    floating.pieces["instance:b"].local_y_mm = 105;
    floating.pieces["instance:b"].outline_mm = [[2400, 105], [2600, 105], [2600, 305], [2400, 305]];
    const suggestion = SnapGeometry.suggestPieceSnap(floating, "instance:a", 2000, 102, {
        magnetEnabled: true,
        thresholdMm: 8,
    });
    assert.equal(suggestion.ok, true);
    assert.match(String(suggestion.source), /align:top:/);
    const proposal = MoveGeometry.proposePieceDrop(
        floating,
        "instance:a",
        2000 + suggestion.dx,
        100 + suggestion.dy
    );
    assert.equal(proposal.ok, true);
    assert.equal(proposal.target_sheet_no, null);
    assert.equal(Math.round(proposal.local_y_mm), 105);
}

// Near-board-size doors stay near both sheets across the editor gap; magnet
// must still target the dominant board's usable edge.
{
    const dual = {
        boards: {
            1: {
                sheet_no: 1,
                origin_x_mm: 0,
                origin_y_mm: 0,
                width_mm: 1220,
                height_mm: 2440,
                trim_x_mm: 0,
                trim_y_mm: 0,
                usable_width_mm: 1220,
                usable_length_mm: 2440,
                title_band_mm: 36,
            },
            2: {
                sheet_no: 2,
                origin_x_mm: 1268,
                origin_y_mm: 0,
                width_mm: 1220,
                height_mm: 2440,
                trim_x_mm: 0,
                trim_y_mm: 0,
                usable_width_mm: 1220,
                usable_length_mm: 2440,
                title_band_mm: 36,
            },
        },
        pieces: {
            "instance:wide": {
                piece_key: "instance:wide",
                piece_id: 10,
                piece_instance_id: "wide",
                sheet_no: 1,
                local_x_mm: 20,
                local_y_mm: 40,
                placement_cm: { x: 2, y: 4, w: 118, h: 100 },
                outline_mm: [[20, 40], [1200, 40], [1200, 1040], [20, 1040]],
                editable: true,
                glass_host_key: null,
            },
        },
        kerf_mm: 4,
        stale_cut_path_sheets: [],
        stale_unbound_text_sheets: [],
    };
    // Mostly over board 2 (origin 1268) while still near board 1 across the gap.
    const suggestion = SnapGeometry.suggestPieceSnap(dual, "instance:wide", 1275, 40, {
        magnetEnabled: true,
        thresholdMm: 40,
    });
    assert.equal(suggestion.ok, true);
    assert.match(String(suggestion.source), /usable/);
    const proposal = MoveGeometry.proposePieceDrop(
        dual,
        "instance:wide",
        20 + suggestion.dx,
        40 + suggestion.dy
    );
    assert.equal(proposal.ok, true);
    assert.equal(Number(proposal.target_sheet_no), 2);
    assert.equal(Math.round(proposal.local_x_mm), 0);
}

// Near-full-board doors need a wider usable-edge capture than the screen-pixel
// threshold; neighbour snaps must keep the normal threshold.
{
    const wideFit = {
        boards: {
            1: {
                sheet_no: 1,
                origin_x_mm: 0,
                origin_y_mm: 0,
                width_mm: 1220,
                height_mm: 2440,
                trim_x_mm: 0,
                trim_y_mm: 0,
                usable_width_mm: 1220,
                usable_length_mm: 2440,
                title_band_mm: 36,
            },
        },
        pieces: {
            "instance:wide": {
                piece_key: "instance:wide",
                piece_id: 11,
                piece_instance_id: "wide",
                sheet_no: 1,
                local_x_mm: 55,
                local_y_mm: 40,
                placement_cm: { x: 5.5, y: 4, w: 110, h: 100 },
                outline_mm: [[55, 40], [1155, 40], [1155, 1040], [55, 1040]],
                editable: true,
                glass_host_key: null,
            },
        },
        kerf_mm: 4,
        stale_cut_path_sheets: [],
        stale_unbound_text_sheets: [],
    };
    // Offset 55mm exceeds the 20mm screen threshold, but the widened usable
    // threshold for near-full doors must still capture the left board edge.
    const suggestion = SnapGeometry.suggestPieceSnap(wideFit, "instance:wide", 55, 40, {
        magnetEnabled: true,
        thresholdMm: 20,
    });
    assert.equal(suggestion.ok, true);
    assert.match(String(suggestion.source), /usable/);
    const proposal = MoveGeometry.proposePieceDrop(
        wideFit,
        "instance:wide",
        55 + suggestion.dx,
        40 + suggestion.dy
    );
    assert.equal(proposal.ok, true);
    assert.equal(Math.round(proposal.local_x_mm), 0);
}

// A 980mm door on a 1210mm sheet used to jump the full 230mm slack once the
// pointer left the widened 145mm board-edge radius. The neighbour alignment
// 15mm from the pointer must win instead.
{
    const slack = 230;
    const alignDx = -165;
    const largeDoor = {
        boards: {
            1: {
                sheet_no: 1,
                origin_x_mm: 0,
                origin_y_mm: 0,
                width_mm: 1210,
                height_mm: 2430,
                trim_x_mm: 0,
                trim_y_mm: 0,
                usable_width_mm: 1210,
                usable_length_mm: 2430,
                title_band_mm: 36,
            },
        },
        pieces: {
            "instance:mover": {
                piece_key: "instance:mover",
                piece_id: 21,
                piece_instance_id: "mover",
                sheet_no: 1,
                local_x_mm: slack,
                local_y_mm: 600,
                placement_cm: { x: 23, y: 60, w: 98, h: 50 },
                outline_mm: [[230, 600], [1210, 600], [1210, 1100], [230, 1100]],
                editable: true,
                glass_host_key: null,
            },
            "instance:neighbour": {
                piece_key: "instance:neighbour",
                piece_id: 22,
                piece_instance_id: "neighbour",
                sheet_no: 1,
                local_x_mm: slack + alignDx,
                local_y_mm: 0,
                placement_cm: { x: 6.5, y: 0, w: 98, h: 50 },
                outline_mm: [[65, 0], [1045, 0], [1045, 500], [65, 500]],
                editable: true,
                glass_host_key: null,
            },
        },
        kerf_mm: 0,
        stale_cut_path_sheets: [],
        stale_unbound_text_sheets: [],
    };
    const near = SnapGeometry.suggestPieceSnap(largeDoor, "instance:mover", slack - 40, 600, {
        magnetEnabled: true,
        thresholdMm: 15.9,
    });
    assert.equal(near.ok, true);
    assert.equal(Math.round(near.dx), 0);
    const towardNeighbour = SnapGeometry.suggestPieceSnap(
        largeDoor,
        "instance:mover",
        slack - 150.8,
        600,
        { magnetEnabled: true, thresholdMm: 15.9 }
    );
    assert.equal(towardNeighbour.ok, true);
    assert.equal(Math.round(towardNeighbour.dx), alignDx);
    assert.match(String(towardNeighbour.source), /neighbour/);
    assert.notEqual(Math.round(towardNeighbour.dx), -slack);
}

console.log("board_editor_snap.test.js: ok");

})();
