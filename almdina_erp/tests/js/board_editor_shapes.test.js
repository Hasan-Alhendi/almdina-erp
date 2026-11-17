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

function shape(drawing) {
    return drawing.current().document.shapes[0];
}

const rectangle = session();
assert.equal(rectangle.createShape("rectangle", {
    x_mm: 100, y_mm: 80, width_mm: 500, height_mm: 300, rotation_deg: 0,
}), true);
assert.equal(shape(rectangle).params.width_mm, 500);
assert.equal(shape(rectangle).params.height_mm, 300);
assert.equal(shape(rectangle).exploded, false);
assert.equal(rectangle.updateShape(shape(rectangle).id, Object.assign({}, shape(rectangle).params, { width_mm: 550 })), true);
assert.equal(shape(rectangle).params.width_mm, 550);
assert.equal(shape(rectangle).params.height_mm, 300);
assert.equal(rectangle.current().document.paths.length, 0);

const circle = session();
assert.equal(circle.createShape("circle", { cx_mm: 200, cy_mm: 200, radius_mm: 100 }), true);
assert.equal(circle.updateShape(shape(circle).id, { cx_mm: 200, cy_mm: 200, radius_mm: 120 }), true);
assert.equal(shape(circle).params.radius_mm, 120);

const ellipse = session();
assert.equal(ellipse.createShape("ellipse", {
    cx_mm: 150, cy_mm: 140, rx_mm: 80, ry_mm: 40, rotation_deg: 15,
}), true);
assert.equal(shape(ellipse).params.ry_mm, 40);

const arc = session();
assert.equal(arc.createShape("arc", {
    cx_mm: 100, cy_mm: 100, radius_mm: 50, start_angle_deg: 0, sweep_angle_deg: 90,
}), true);
assert.equal(Space.normalizeShape("arc", shape(arc).params).figure.closed, false);

const polygon = session();
assert.equal(polygon.createShape("polygon", {
    cx_mm: 100, cy_mm: 100, radius_mm: 40, sides: 5, rotation_deg: 0,
}), true);
assert.equal(Space.normalizeShape("polygon", shape(polygon).params).figure.points.length, 5);
assert.equal(polygon.createShape("polygon", {
    cx_mm: 0, cy_mm: 0, radius_mm: 10, sides: 2, rotation_deg: 0,
}), false);

const trapezoid = session();
assert.equal(trapezoid.createShape("trapezoid", {
    x_mm: 0, y_mm: 0, bottom_width_mm: 200, top_width_mm: 100, height_mm: 80,
}), true);
const trapPoints = Space.normalizeShape("trapezoid", shape(trapezoid).params).figure.points;
assert.equal(trapPoints[0].x, 50);
assert.equal(trapPoints[1].x, 150);

const lShape = session();
assert.equal(lShape.createShape("l_shape", {
    x_mm: 0, y_mm: 0, width_mm: 300, height_mm: 200, notch_width_mm: 80, notch_height_mm: 60,
}), true);
assert.equal(Space.normalizeShape("l_shape", shape(lShape).params).figure.points.length, 6);
const invalidL = JSON.stringify(lShape.current().document);
assert.equal(lShape.createShape("l_shape", {
    x_mm: 0, y_mm: 0, width_mm: 100, height_mm: 80, notch_width_mm: 100, notch_height_mm: 20,
}), false);
assert.equal(lShape.current().errorCode, "invalid_shape");
assert.equal(JSON.stringify(lShape.current().document), invalidL);

const clipped = session();
assert.equal(clipped.createShape("clipped_corner", {
    x_mm: 10, y_mm: 10, width_mm: 200, height_mm: 150, cut_width_mm: 40, cut_height_mm: 25, corner: "top_right",
}), true);
assert.equal(Space.normalizeShape("clipped_corner", shape(clipped).params).figure.points.length, 5);

const curve = session();
assert.equal(curve.createBezier({ x: 0, y: 0 }, { x: 120, y: 0 }), true);
const bezier = curve.current().document.paths[0].segments[0];
assert.equal(bezier.kind, "bezier");
assert.equal(bezier.controls.length, 2);
assert.equal(curve.moveBezierControl(curve.current().document.paths[0].id, bezier.id, 0, bezier.controls[0].x_mm, 45), true);
assert.equal(curve.current().document.paths[0].segments[0].controls[0].y_mm, 45);
assert.equal(curve.current().document.shapes.length, 0);

const converted = session();
converted.createShape("rectangle", { x_mm: 0, y_mm: 0, width_mm: 500, height_mm: 300, rotation_deg: 0 });
const shapeId = shape(converted).id;
assert.equal(converted.convertShape(shapeId), true);
const convertedShape = converted.current().document.shapes[0];
const convertedPath = converted.current().document.paths[0];
assert.equal(convertedShape.exploded, true);
assert.equal(convertedShape.path_id, convertedPath.id);
assert.equal(convertedPath.source_shape_id, shapeId);
assert.equal(convertedPath.closed, true);
assert.equal(convertedPath.nodes.length, 4);
assert.equal(convertedPath.nodes[1].x_mm, 500);
assert.equal(convertedPath.nodes[1].y_mm, 0);
assert.equal(convertedPath.segments[convertedPath.segments.length - 1].to_node, convertedPath.nodes[0].id);
assert.equal(converted.current().document.shapes.filter((row) => !row.exploded).length, 0);

const nodeId = convertedPath.nodes[1].id;
assert.equal(converted.moveNode(convertedPath.id, nodeId, 540, 0), true);
assert.equal(converted.current().document.paths[0].nodes[1].x_mm, 540);
assert.equal(converted.current().document.paths[0].segments[0].to_node, nodeId);
assert.equal(converted.current().document.paths[0].segments[1].from_node, nodeId);
assert.equal(converted.current().document.paths[0].closed, true);
const segmentId = converted.current().document.paths[0].segments[0].id;
assert.equal(converted.insertNode(convertedPath.id, segmentId, 270, 0), true);
assert.equal(converted.current().document.paths[0].nodes.length, 5);
assert.equal(converted.current().document.paths[0].closed, true);
const inserted = converted.current().document.paths[0].nodes.find((node) => node.x_mm === 270);
assert.equal(converted.deleteNode(convertedPath.id, inserted.id), true);
assert.equal(converted.current().document.paths[0].nodes.length, 4);
assert.equal(converted.current().document.paths[0].closed, true);
assert.equal(converted.current().document.paths[0].segments.some((segment) => (
    !converted.current().document.paths[0].nodes.some((node) => node.id === segment.from_node)
    || !converted.current().document.paths[0].nodes.some((node) => node.id === segment.to_node)
)), false);
const unchanged = JSON.stringify(converted.current().document);
assert.equal(converted.moveNode(convertedPath.id, converted.current().document.paths[0].nodes[0].id, 540, 0), false);
assert.equal(JSON.stringify(converted.current().document), unchanged);

converted.current().selection = {
    pathId: convertedPath.id,
    segmentId: converted.current().document.paths[0].segments[0].id,
};
assert.equal(converted.editSelected(200, 0), true);
assert.equal(converted.current().document.paths[0].closed, true);
assert.equal(converted.current().document.paths[0].segments.at(-1).to_node, converted.current().document.paths[0].nodes[0].id);

const history = session();
assert.equal(history.createShape("circle", { cx_mm: 10, cy_mm: 10, radius_mm: 25 }), true);
assert.equal(history.undo(), true);
assert.equal(history.current().document.shapes.length, 0);
assert.equal(history.redo(), true);
assert.equal(history.current().document.shapes[0].params.radius_mm, 25);

const saved = JSON.parse(JSON.stringify(history.current().document));
const reopened = Model.createSession();
reopened.activate({ pieceInstanceId: "piece:special", widthMm: 600, lengthMm: 2100 });
const ticket = reopened.beginLoad();
assert.equal(reopened.applyLoaded(ticket.pieceInstanceId, ticket.token, {
    ok: true,
    drawing: saved,
    drawing_version: 4,
}), true);
assert.equal(reopened.current().document.shapes[0].params.radius_mm, 25);
assert.equal(reopened.current().document.shapes[0].kind, "circle");

const frame = Space.pieceFrame({
    sheet_no: 1,
    rotation_deg: 90,
    placement_cm: { x: 0, y: 0 },
    entry_pivot_mm: { x: 0, y: 0 },
    pivot_mm: { x: 0, y: 0 },
}, { 1: { origin_x_mm: 0, origin_y_mm: 0 } }, { widthMm: 600 });
const local = Space.normalizeShape("rectangle", shape(rectangle).params).figure.points[1];
const screen = Space.doorToWorld(frame, local.x, local.y);
assert.equal(shape(rectangle).params.width_mm, 550);
assert.ok(Math.abs(screen.x - local.x) > 1 || Math.abs(screen.y - local.y) > 1);

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
rectangle.moveShape(shape(rectangle).id, 5, 0);
assert.equal(shape(rectangle).params.x_mm, 105);
assert.equal(JSON.stringify(store.snapshot().session), fingerprint);
assert.equal(store.snapshot().canUndo, false);

const dom = load([
    "public/js/board_editor/drawing_space.js",
    "public/js/board_editor/drawing_model.js",
    "public/js/board_editor/editor_mode.js",
    "public/js/board_editor/canvas_renderer.js",
    "public/js/board_editor/drawing_properties_panel.js",
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
const drawing = Model.createSession();
drawing.activate({ pieceInstanceId: "piece:special", widthMm: 600, lengthMm: 2100 });
drawing.markReady();
let drawingClicks = 0;
const view = {
    editorMode: "drawing",
    canSaveLayout: true,
    drawingTarget: { status: "special", canEdit: true, label: "Special door", widthCm: 60, lengthCm: 210 },
    drawingView: {
        tool: "shapes",
        shapeKind: "rectangle",
        ready: true,
        shapeForm: {
            mode: "create",
            fields: [
                { key: "x_mm", labelKey: "X (mm)", value: "100" },
                { key: "y_mm", labelKey: "Y (mm)", value: "80" },
                { key: "width_mm", labelKey: "Width (mm)", value: "" },
                { key: "height_mm", labelKey: "Height (mm)", value: "" },
                { key: "rotation_deg", labelKey: "Angle (°)", value: "0" },
            ],
            actions: {},
        },
        paths: [],
        shapes: [],
    },
    viewport: { scale: 1 },
    session: { pieces: {}, boards: {} },
    selectedPieceKeys: [],
};
const properties = new dom.MiniElement("aside", {}, dom.document);
const shapeHandlers = {
    drawingPointerDown() { drawingClicks += 1; return true; },
    commitShapeForm() {
        const fields = {};
        properties.querySelectorAll("[data-abe-shape-field]").forEach((input) => {
            fields[input.getAttribute("data-abe-shape-field")] = input.value;
        });
        drawing.commitShapeFields("rectangle", fields, { x: 100, y: 80 }, "create");
    },
};
dom.AlmdinaBoardEditor.CanvasRenderer.render(host, view, shapeHandlers);
dom.AlmdinaBoardEditor.DrawingProperties.render(properties, view, shapeHandlers);
assert.ok(host.querySelectorAll("[data-abe-drawing-tool]").some((node) => node.getAttribute("data-abe-drawing-tool") === "shapes"));
assert.equal(properties.querySelector('[data-abe-shape-kind="rectangle"]').getAttribute("data-abe-shape-kind"), "rectangle");
const width = properties.querySelector('[data-abe-shape-field="width_mm"]');
const height = properties.querySelector('[data-abe-shape-field="height_mm"]');
width.value = "500";
height.value = "300";
const enter = { key: "Enter", code: "Enter", defaultPrevented: false, cancelBubble: false, preventDefault() { this.defaultPrevented = true; }, stopPropagation() { this.cancelBubble = true; }, target: height };
(height.listeners.keydown || []).forEach((fn) => fn(enter));
assert.equal(enter.defaultPrevented, true);
assert.equal(drawing.current().document.shapes[0].params.width_mm, 500);
assert.equal(drawing.current().document.shapes[0].params.height_mm, 300);
assert.equal(drawingClicks, 0);
const pointerEvent = { button: 0, cancelBubble: false, stopPropagation() { this.cancelBubble = true; }, target: width };
let node = width;
while (node) {
    if (pointerEvent.cancelBubble) break;
    (node.listeners.pointerdown || []).forEach((fn) => fn(pointerEvent));
    node = node.parentElement;
}
assert.equal(hostEvents, 0);
assert.equal(drawingClicks, 0);
const figure = Space.normalizeShape("rectangle", drawing.current().document.shapes[0].params).figure;
view.drawingView.shapes = [{
    id: drawing.current().document.shapes[0].id,
    closed: true,
    selected: true,
    points: figure.points,
    handles: figure.handles,
}];
view.drawingView.shapeForm = null;
dom.AlmdinaBoardEditor.CanvasRenderer.render(host, view, {});
const drawnShape = host.querySelector("[data-abe-drawing-shape]");
assert.ok(drawnShape);
assert.match(drawnShape.getAttribute("d"), /600 80/);
assert.match(drawnShape.getAttribute("d"), /100 380/);

const controller = fs.readFileSync(path.join(root, "public/js/board_editor/controller.js"), "utf8");
assert.match(controller, /commitShapeFields\(/);
assert.match(controller, /createShape\(/);
assert.match(controller, /moveNode\(/);
assert.doesNotMatch(controller, /special_shape_geometry_json|layout_json|snapshot_json/);
assert.equal(Space.computePolylineHudPosition, undefined);
assert.equal(typeof dom.AlmdinaBoardEditor.CanvasRenderer.computePolylineHudPosition, "function");
const hud = dom.AlmdinaBoardEditor.CanvasRenderer.computePolylineHudPosition({
    startX: 120, startY: 200, endX: 420, endY: 210, width: 180, height: 28, previousSide: "left",
    bounds: { left: 0, top: 0, right: 900, bottom: 600 },
});
const hudFurther = dom.AlmdinaBoardEditor.CanvasRenderer.computePolylineHudPosition({
    startX: 120, startY: 200, endX: 620, endY: 260, width: 180, height: 28, previousSide: "right",
    bounds: { left: 0, top: 0, right: 900, bottom: 600 },
});
assert.equal(hud.left, hudFurther.left);
assert.equal(hud.top, hudFurther.top);

console.log("board editor shape tests ok");
