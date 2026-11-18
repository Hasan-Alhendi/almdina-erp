"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.resolve(__dirname, "../..");
const context = {
    console,
    __: (message) => message,
    document: { createElementNS() { return { setAttribute() {}, appendChild() {} }; } },
};
context.window = context;
context.globalThis = context;
vm.createContext(context);
["public/js/board_editor/drawing_space.js", "public/js/board_editor/drawing_model.js", "public/js/board_editor/drawing_compile.js"].forEach((relative) => {
    vm.runInContext(fs.readFileSync(path.join(root, relative), "utf8"), context, { filename: relative });
});
const Space = context.AlmdinaBoardEditor.DrawingSpace;
const Model = context.AlmdinaBoardEditor.DrawingModel;
const Compile = context.AlmdinaBoardEditor.DrawingCompile;

function session() {
    const drawing = Model.createSession();
    drawing.activate({ pieceInstanceId: "piece:special", widthMm: 2000, lengthMm: 3000 });
    drawing.markReady();
    return drawing;
}

function near(actual, expected, epsilon = 0.02) {
    assert.ok(Math.abs(actual - expected) <= epsilon, `${actual} is not near ${expected}`);
}

function rect(drawing, params) {
    assert.equal(drawing.createShape("rectangle", Object.assign({
        x_mm: 0, y_mm: 0, width_mm: 100, height_mm: 50, rotation_deg: 0,
    }, params)), true);
    return drawing.current().document.shapes[0];
}

const corners = {
    nw: { x: 10, y: 10 },
    ne: { x: 80, y: 10 },
    se: { x: 80, y: 40 },
    sw: { x: 10, y: 40 },
};
Object.entries(corners).forEach(([handle, point]) => {
    const drawing = session();
    const shape = rect(drawing);
    assert.equal(drawing.resizeShape(shape.id, handle, point, { base: shape.params }), true);
    const params = drawing.current().document.shapes[0].params;
    const frame = Space.shapeFrame("rectangle", params);
    const fixed = {
        nw: { x: 100, y: 50 },
        ne: { x: 0, y: 50 },
        se: { x: 0, y: 0 },
        sw: { x: 100, y: 0 },
    }[handle];
    const fixedX = handle === "nw" || handle === "sw" ? frame.pivot.x + frame.width : frame.pivot.x;
    const fixedY = handle === "nw" || handle === "ne" ? frame.pivot.y + frame.height : frame.pivot.y;
    near(fixedX, fixed.x);
    near(fixedY, fixed.y);
    assert.ok(params.width_mm > 0 && params.height_mm > 0);
});

["n", "e", "s", "w"].forEach((handle) => {
    const drawing = session();
    const shape = rect(drawing);
    const point = { n: { x: 40, y: -20 }, e: { x: 160, y: 20 }, s: { x: 40, y: 80 }, w: { x: -30, y: 20 } }[handle];
    assert.equal(drawing.resizeShape(shape.id, handle, point, { base: shape.params }), true);
    const params = drawing.current().document.shapes[0].params;
    if (handle === "e" || handle === "w") near(params.height_mm, 50);
    else near(params.width_mm, 100);
    if (handle === "e") near(params.x_mm, 0);
    if (handle === "w") near(params.x_mm + params.width_mm, 100);
    if (handle === "s") near(params.y_mm, 0);
    if (handle === "n") near(params.y_mm + params.height_mm, 50);
});

{
    const drawing = session();
    const shape = rect(drawing);
    assert.equal(drawing.resizeShape(shape.id, "se", { x: 200, y: 40 }, { base: shape.params, aspect: true }), true);
    const params = drawing.current().document.shapes[0].params;
    near(params.width_mm / params.height_mm, 2);
    near(params.x_mm, 0);
    near(params.y_mm, 0);
}

{
    const drawing = session();
    const shape = rect(drawing);
    const before = Object.assign({}, shape.params);
    assert.equal(drawing.transformShape(shape.id, { width: 80 }), true);
    const center = Space.shapeFrame("rectangle", drawing.current().document.shapes[0].params).center;
    near(center.x, 50);
    near(center.y, 25);
    assert.equal(drawing.transformShape(shape.id, { height: 20 }), true);
    assert.equal(drawing.transformShape(shape.id, { rotation: 90 }), true);
    const turned = drawing.current().document.shapes[0].params;
    near(turned.rotation_deg, 90);
    near(turned.width_mm, 80);
    near(turned.height_mm, 20);
    const turnedCenter = Space.shapeFrame("rectangle", turned).center;
    near(turnedCenter.x, 50);
    near(turnedCenter.y, 25);
    assert.equal(drawing.transformShape(shape.id, { x: 70 }), true);
    const moved = Space.shapeFrame("rectangle", drawing.current().document.shapes[0].params);
    near(moved.center.x, 70);
    near(moved.width, before.width_mm === 100 ? moved.width : moved.width);
    near(moved.width, 80);
    near(moved.height, 20);
}

{
    const drawing = session();
    const shape = rect(drawing, { rotation_deg: 90 });
    const base = Space.shapeFrame("rectangle", shape.params);
    const east = Space.handleLocalPoint(base, "e");
    const target = Space.rotate({ x: east.x + 30, y: east.y }, base.center, 0);
    // Drag further along the local +u axis, which is rotated 90°.
    const localEnd = { x: base.pivot.x, y: base.pivot.y };
    void localEnd;
    const further = Space.rotate(
        { x: base.center.x + (base.width / 2 + 30), y: base.center.y },
        base.center,
        base.rotation
    );
    assert.equal(drawing.resizeShape(shape.id, "e", further, { base: shape.params }), true);
    const next = drawing.current().document.shapes[0].params;
    near(next.height_mm, 50);
    near(next.width_mm, 130);
    near(next.rotation_deg, 90);
    void target;
}

{
    const drawing = session();
    assert.equal(drawing.createShape("circle", { cx_mm: 40, cy_mm: 40, radius_mm: 20 }), true);
    const shape = drawing.current().document.shapes[0];
    assert.equal(drawing.resizeShape(shape.id, "e", { x: 80, y: 40 }, { base: shape.params }), true);
    const params = drawing.current().document.shapes[0].params;
    near(params.radius_mm, 30);
    assert.equal(params.rx_mm, undefined);
}

{
    const drawing = session();
    assert.equal(drawing.createBezier({ x: 0, y: 0 }, { x: 90, y: 0 }), true);
    const path = drawing.current().document.paths[0];
    const before = JSON.parse(JSON.stringify(path.segments[0].controls));
    const frame = Space.pointsFrame(path.nodes.map((node) => ({ x: node.x_mm, y: node.y_mm })).concat(before.map((point) => ({ x: point.x_mm, y: point.y_mm }))), 0, false);
    assert.equal(drawing.resizePath(path.id, "e", { x: frame.pivot.x + frame.width + 30, y: frame.center.y }, { base: JSON.parse(JSON.stringify(path)) }), true);
    const next = drawing.current().document.paths[0];
    assert.equal(next.segments[0].kind, "bezier");
    assert.ok(next.segments[0].controls[0].x_mm > before[0].x_mm);
    assert.equal(drawing.undo(), true);
    near(drawing.current().document.paths[0].segments[0].controls[0].x_mm, before[0].x_mm);
    assert.equal(drawing.redo(), true);
    assert.ok(drawing.current().document.paths[0].segments[0].controls[0].x_mm > before[0].x_mm);
}

{
    const drawing = session();
    const shape = rect(drawing);
    drawing.current().document.blank.width_mm = 2000;
    assert.equal(drawing.resizeShape(shape.id, "se", { x: 40, y: 20 }, { base: shape.params }), true);
    assert.equal(drawing.current().document.blank.width_mm, 2000);
    assert.equal(drawing.current().document.blank.length_mm, 3000);
}

{
    const drawing = session();
    assert.equal(drawing.createBezier({ x: 10, y: 10 }, { x: 80, y: 10 }), true);
    const path = drawing.current().document.paths[0];
    path.closed = true;
    path.role = "manufacturing_outer";
    const before = Compile.compile(drawing.current().document, 2000, 3000);
    assert.equal(drawing.resizePath(path.id, "e", { x: 4000, y: 10 }, { base: JSON.parse(JSON.stringify(path)) }), true);
    const after = Compile.compile(drawing.current().document, 2000, 3000);
    assert.notEqual(JSON.stringify(before), JSON.stringify(after));
    assert.equal(after.status, "rejected");
}

{
    const frame = { entryOrigin: { x: 0, y: 0 }, entryPivot: { x: 0, y: 0 }, livePivot: { x: 0, y: 0 }, translation: { x: 0, y: 0 }, rotationDeg: 90, flipH: true, flipV: false, sourceRotated: false, blankWidthMm: 200, boardOrigin: { x: 15, y: 25 } };
    const door = { x: 40, y: 70 };
    const world = Space.doorToWorld(frame, door.x, door.y);
    const back = Space.worldToDoor(frame, world.x, world.y);
    near(back.x, door.x);
    near(back.y, door.y);
    const drawing = session();
    const shape = rect(drawing);
    assert.equal(drawing.resizeShape(shape.id, "e", { x: 140, y: 25 }, { base: shape.params }), true);
    near(drawing.current().document.shapes[0].params.width_mm, 140);
}

{
    assert.equal(Space.resizeCursor(10, 0), "ew-resize");
    assert.equal(Space.resizeCursor(0, 10), "ns-resize");
    assert.equal(Space.resizeCursor(10, 10), "nwse-resize");
    assert.equal(Space.resizeCursor(10, -10), "nesw-resize");
    const drawing = session();
    const shape = rect(drawing, { rotation_deg: 90 });
    const frame = Space.shapeFrame("rectangle", shape.params);
    const east = Space.handleLocalPoint(frame, "e");
    assert.equal(Space.resizeCursor(east.x - frame.center.x, east.y - frame.center.y), "ns-resize");
}

{
    const drawing = session();
    const shape = rect(drawing);
    const base = JSON.parse(JSON.stringify(shape.params));
    assert.equal(drawing.resizeShape(shape.id, "se", { x: 180, y: 40 }, { base, aspect: false, history: false }), true);
    assert.equal(drawing.resizeShape(shape.id, "se", { x: 180, y: 40 }, { base, aspect: true, history: false }), true);
    const params = drawing.current().document.shapes[0].params;
    near(params.width_mm / params.height_mm, 2);
    near(params.x_mm, 0);
    near(params.y_mm, 0);
}

{
    const drawing = session();
    const shape = rect(drawing);
    assert.equal(drawing.transformShape(shape.id, { width: 0 }), false);
    assert.equal(drawing.transformShape(shape.id, { width: -4 }), false);
    near(drawing.current().document.shapes[0].params.width_mm, 100);
    assert.equal(drawing.transformShape(shape.id, { width: 80 }), true);
    assert.equal(drawing.undo(), true);
    near(drawing.current().document.shapes[0].params.width_mm, 100);
    assert.equal(drawing.redo(), true);
    near(drawing.current().document.shapes[0].params.width_mm, 80);
}

{
    const drawing = session();
    assert.equal(drawing.createShape("ellipse", { cx_mm: 40, cy_mm: 30, rx_mm: 20, ry_mm: 10, rotation_deg: 0 }), true);
    const shape = drawing.current().document.shapes[0];
    assert.equal(drawing.resizeShape(shape.id, "e", { x: 80, y: 30 }, { base: shape.params }), true);
    const params = drawing.current().document.shapes[0].params;
    assert.equal(params.kind, undefined);
    near(params.rx_mm, 30);
    near(params.ry_mm, 10);
    assert.equal(drawing.current().document.shapes[0].kind, "ellipse");
}

{
    const drawing = session();
    assert.equal(drawing.createShape("circle", { cx_mm: 40, cy_mm: 40, radius_mm: 20 }), true);
    const shape = drawing.current().document.shapes[0];
    assert.equal(drawing.transformShape(shape.id, { rotation: 45 }), true);
    near(drawing.current().document.shapes[0].params.radius_mm, 20);
    near(drawing.current().document.shapes[0].params.cx_mm, 40);
}

{
    const drawing = session();
    assert.equal(drawing.createShape("polygon", { cx_mm: 50, cy_mm: 50, radius_mm: 20, sides: 5, rotation_deg: 0 }), true);
    const shape = drawing.current().document.shapes[0];
    const frame = Space.shapeFrame("polygon", shape.params);
    const east = Space.handleLocalPoint(frame, "e");
    assert.equal(drawing.resizeShape(shape.id, "e", { x: east.x + 10, y: east.y }, { base: shape.params }), true);
    const params = drawing.current().document.shapes[0].params;
    assert.equal(drawing.current().document.shapes[0].kind, "polygon");
    assert.equal(params.sides, 5);
    assert.ok(params.radius_mm > 20);
    near(params.rotation_deg, 0);
}

{
    const drawing = session();
    assert.equal(drawing.createShape("arc", {
        cx_mm: 40, cy_mm: 40, radius_mm: 20, start_angle_deg: 10, sweep_angle_deg: 70, rotation_deg: 0,
    }), true);
    const shape = drawing.current().document.shapes[0];
    const frame = Space.shapeFrame("arc", shape.params);
    const east = Space.handleLocalPoint(frame, "e");
    assert.equal(drawing.resizeShape(shape.id, "e", { x: east.x + 16, y: east.y + 4 }, { base: shape.params }), true);
    const params = drawing.current().document.shapes[0].params;
    assert.equal(drawing.current().document.shapes[0].kind, "arc");
    near(params.start_angle_deg, 10);
    near(params.sweep_angle_deg, 70);
    assert.ok(params.radius_mm > 20);
    const next = Space.shapeFrame("arc", params);
    near(next.width, next.height);
}

{
    const drawing = session();
    assert.equal(drawing.createShape("trapezoid", {
        x_mm: 0, y_mm: 0, bottom_width_mm: 100, top_width_mm: 60, height_mm: 40, rotation_deg: 0,
    }), true);
    const shape = drawing.current().document.shapes[0];
    assert.equal(drawing.resizeShape(shape.id, "e", { x: 140, y: 20 }, { base: shape.params }), true);
    const params = drawing.current().document.shapes[0].params;
    assert.equal(drawing.current().document.shapes[0].kind, "trapezoid");
    near(params.bottom_width_mm, 140);
    near(params.top_width_mm, 84);
    near(params.height_mm, 40);
    near(params.x_mm, 0);
}

{
    const drawing = session();
    assert.equal(drawing.createShape("l_shape", {
        x_mm: 0, y_mm: 0, width_mm: 90, height_mm: 60, notch_width_mm: 30, notch_height_mm: 20, rotation_deg: 0,
    }), true);
    const shape = drawing.current().document.shapes[0];
    assert.equal(drawing.resizeShape(shape.id, "e", { x: 120, y: 30 }, { base: shape.params }), true);
    const params = drawing.current().document.shapes[0].params;
    assert.equal(drawing.current().document.shapes[0].kind, "l_shape");
    near(params.width_mm, 120);
    near(params.height_mm, 60);
    near(params.notch_width_mm, 40);
    near(params.notch_height_mm, 20);
}

{
    const drawing = session();
    assert.equal(drawing.createShape("clipped_corner", {
        x_mm: 0, y_mm: 0, width_mm: 80, height_mm: 50, cut_width_mm: 16, cut_height_mm: 10, corner: "top_right", rotation_deg: 0,
    }), true);
    const shape = drawing.current().document.shapes[0];
    assert.equal(drawing.resizeShape(shape.id, "s", { x: 40, y: 75 }, { base: shape.params }), true);
    const params = drawing.current().document.shapes[0].params;
    assert.equal(drawing.current().document.shapes[0].kind, "clipped_corner");
    near(params.width_mm, 80);
    near(params.height_mm, 75);
    near(params.cut_width_mm, 16);
    near(params.cut_height_mm, 15);
    assert.equal(params.corner, "top_right");
}

{
    const piece = {
        entryOrigin: { x: 0, y: 0 }, entryPivot: { x: 0, y: 0 }, livePivot: { x: 0, y: 0 },
        translation: { x: 0, y: 0 }, rotationDeg: 90, flipH: true, flipV: true,
        sourceRotated: false, blankWidthMm: 200, boardOrigin: { x: 15, y: 25 },
    };
    const door = { x: 40, y: 70 };
    const world = Space.doorToWorld(piece, door.x, door.y);
    [1, 4].forEach((scale) => {
        const camera = { scale, scrollX: 12, scrollY: 30, padX: 8, padY: 8, minX: 0, minY: 0 };
        const screen = Space.worldToScreen(world, camera);
        const backWorld = Space.screenToWorld(screen, camera);
        const backDoor = Space.worldToDoor(piece, backWorld.x, backWorld.y);
        near(backDoor.x, door.x);
        near(backDoor.y, door.y);
    });
    const drawing = session();
    const shape = rect(drawing);
    assert.equal(drawing.resizeShape(shape.id, "e", door, { base: shape.params }), true);
    near(drawing.current().document.shapes[0].params.width_mm, 40);
}

{
    const drawing = session();
    const shape = rect(drawing, { rotation_deg: 15 });
    const before = Space.shapeFrame("rectangle", shape.params).center;
    assert.equal(drawing.transformShape(shape.id, { width: 120 }), true);
    const payload = JSON.parse(JSON.stringify(drawing.current().document));
    const reopened = session();
    const load = reopened.beginLoad();
    assert.equal(reopened.applyLoaded(load.pieceInstanceId, load.token, {
        ok: true,
        drawing: payload,
        drawing_version: 3,
    }), true);
    const params = reopened.current().document.shapes[0].params;
    near(params.width_mm, 120);
    near(params.rotation_deg, 15);
    const center = Space.shapeFrame("rectangle", params).center;
    near(center.x, before.x);
    near(center.y, before.y);
}

{
    const controller = fs.readFileSync(path.join(root, "public/js/board_editor/controller.js"), "utf8");
    const resizeBody = controller.slice(controller.indexOf("function updateResize"), controller.indexOf("function updateSelectGesture"));
    const endBody = controller.slice(controller.indexOf("function endVectorGesture"), controller.indexOf("function refreshCutValidation"));
    assert.doesNotMatch(resizeBody, /viewport/);
    assert.doesNotMatch(endBody, /viewport/);
    const canvas = fs.readFileSync(path.join(root, "public/js/board_editor/canvas_renderer.js"), "utf8");
    assert.match(canvas, /drawing\.tool === "select" && path\.selected/);
    assert.match(canvas, /resize && drawing\.tool === "select"/);
    assert.match(canvas, /8 \/ safeScale/);
    assert.match(canvas, /18 \/ safeScale/);
    assert.match(canvas, /data-abe-text-handle/);
    assert.match(canvas, /data-abe-reference/);
    const properties = fs.readFileSync(path.join(root, "public/js/board_editor/drawing_properties_panel.js"), "utf8");
    assert.match(properties, /data-abe-transform-field/);
    assert.match(properties, /Lock aspect ratio/);
    assert.match(properties, /drawing\.resizing \? "live"/);
}

const page = fs.readFileSync(path.join(root, "almdina_erp/page/board_editor/board_editor.js"), "utf8");
assert.match(page, /drawing_space\.js\?v=6/);
assert.match(page, /drawing_model\.js\?v=12/);

console.log("board editor resize tests passed");
