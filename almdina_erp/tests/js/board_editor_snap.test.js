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
assert.match(page, /canvas_renderer\.js\?v=55/);
assert.match(page, /controller\.js\?v=53/);
assert.match(page, /board_editor\.css\?v=50/);

console.log("board editor snap tests ok");
