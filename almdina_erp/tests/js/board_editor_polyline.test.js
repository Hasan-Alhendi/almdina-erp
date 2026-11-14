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
    "public/js/board_editor/session_document.js",
    "public/js/board_editor/move_geometry.js",
    "public/js/board_editor/rotation_geometry.js",
    "public/js/board_editor/store.js",
]);
const Space = editor.DrawingSpace;
const Model = editor.DrawingModel;

function readySession() {
    const session = Model.createSession();
    session.activate({ pieceInstanceId: "piece:a", widthMm: 600, lengthMm: 2100 });
    session.markReady();
    return session;
}

function nodes(session) {
    return session.current().document.paths[0].nodes;
}

const drawn = readySession();
assert.equal(drawn.placePoint(0, 0), true);
assert.equal(drawn.current().document.paths.length, 0);
assert.equal(drawn.placePolar(350, 0), true);
assert.equal(nodes(drawn)[1].x_mm, 350);
assert.equal(nodes(drawn)[1].y_mm, 0);
assert.equal(drawn.placePolar(120, 90), true);
assert.equal(nodes(drawn).length, 3);
assert.equal(nodes(drawn)[1].id, drawn.current().document.paths[0].segments[0].to_node);
assert.equal(nodes(drawn)[1].id, drawn.current().document.paths[0].segments[1].from_node);
assert.equal(nodes(drawn)[2].x_mm, 350);
assert.equal(nodes(drawn)[2].y_mm, 120);
assert.equal(drawn.current().document.paths[0].closed, false);
assert.equal(drawn.current().document.paths[0].role, "construction");

[0, 90, 180, 270].forEach((angle) => {
    const session = readySession();
    session.placePoint(10, 20);
    assert.equal(session.placePolar(100, angle), true);
    const measured = session.metrics(session.current().document.paths[0].id, session.current().document.paths[0].segments[0].id);
    assert.ok(Math.abs(measured.lengthMm - 100) < 0.02, String(angle));
    const delta = Math.abs(measured.angleDeg - angle);
    assert.ok(Math.min(delta, 360 - delta) < 0.02, String(measured.angleDeg));
});

const mixed = readySession();
mixed.placePoint(0, 0);
assert.equal(mixed.placePolar(350, 0), true);
assert.equal(mixed.placePoint(350, 80), true);
assert.equal(nodes(mixed)[2].y_mm, 80);

assert.equal(Space.snapAngleDeg(22, true), 15);
assert.equal(Space.snapAngleDeg(23, true), 30);
assert.equal(Space.snapAngleDeg(22, false), 22);

const zero = readySession();
zero.placePoint(0, 0);
zero.placePolar(40, 0);
const beforeZero = JSON.stringify(zero.current().document);
assert.equal(zero.placePolar(0, 0), false);
assert.equal(JSON.stringify(zero.current().document), beforeZero);
assert.equal(zero.current().errorCode, "zero_length");

const closed = readySession();
closed.placePoint(0, 0);
closed.placePolar(100, 0);
closed.placePolar(50, 90);
const startId = nodes(closed)[0].id;
assert.equal(closed.close(), true);
const closedPath = closed.current().document.paths[0];
assert.equal(closedPath.closed, true);
assert.equal(closedPath.nodes.length, 3);
assert.equal(closedPath.segments[closedPath.segments.length - 1].to_node, startId);
assert.equal(closedPath.nodes.filter((node) => node.id === startId).length, 1);

const edited = readySession();
edited.placePoint(0, 0);
edited.placePolar(350, 0);
edited.placePolar(120, 90);
const firstSegment = edited.current().document.paths[0].segments[0].id;
edited.current().selection = { pathId: edited.current().document.paths[0].id, segmentId: firstSegment };
assert.equal(edited.editSelected(400, 0), true);
assert.equal(nodes(edited)[1].x_mm, 400);
assert.equal(nodes(edited)[2].x_mm, 400);
assert.equal(nodes(edited)[2].y_mm, 120);
assert.equal(edited.editSelected(350, 90), true);
assert.ok(Math.abs(nodes(edited)[1].x_mm) < 0.02);
assert.ok(Math.abs(nodes(edited)[1].y_mm - 350) < 0.02);
assert.ok(Math.abs(nodes(edited)[2].y_mm - 470) < 0.02);

const blocked = readySession();
blocked.placePoint(0, 0);
blocked.placePolar(30, 0);
blocked.placePolar(20, 90);
blocked.close();
blocked.current().selection = {
    pathId: blocked.current().document.paths[0].id,
    segmentId: blocked.current().document.paths[0].segments[0].id,
};
assert.equal(blocked.editSelected(80, 0), true);
assert.equal(blocked.current().document.paths[0].closed, true);
assert.equal(blocked.current().document.paths[0].segments[blocked.current().document.paths[0].segments.length - 1].to_node, nodes(blocked)[0].id);
assert.equal(nodes(blocked)[0].x_mm, 0);
assert.equal(nodes(blocked)[1].x_mm, 80);
assert.equal(nodes(blocked)[1].y_mm, 0);
assert.equal(nodes(blocked)[2].x_mm, 30);
assert.equal(nodes(blocked)[2].y_mm, 20);
assert.equal(blocked.editSelected(0, 0), false);
assert.equal(blocked.current().errorCode, "zero_length");
assert.equal(nodes(blocked)[1].x_mm, 80);

const history = readySession();
assert.equal(history.undo(), false);
history.placePoint(0, 0);
history.placePolar(350, 0);
history.finish();
assert.equal(history.current().cursor, null);
assert.equal(history.close(), false);
assert.equal(history.undo(), true);
assert.ok(history.current().cursor);
assert.equal(history.current().document.paths[0].closed, false);
assert.equal(history.undo(), true);
assert.equal(history.current().document.paths.length, 0);
assert.equal(history.redo(), true);
assert.equal(history.current().document.paths[0].nodes[1].x_mm, 350);
history.deleteSelection();
assert.equal(history.current().document.paths.length, 0);
assert.equal(history.undo(), true);
assert.equal(history.current().document.paths.length, 1);

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
store.noteDraftBaseline({ canSaveLayout: true, draftVersion: 1, savedFingerprint: editor.SessionDocument.distributionFingerprint(layout) });
const fingerprint = store.snapshot().distributionFingerprint || editor.SessionDocument.distributionFingerprint(store.snapshot().session);
const before = editor.SessionDocument.distributionFingerprint(store.snapshot().session);
history.placePoint(5, 5);
assert.equal(editor.SessionDocument.distributionFingerprint(store.snapshot().session), before);
assert.equal(store.snapshot().canUndo, false);
assert.equal(store.snapshot().distributionDirty, false);
assert.equal(fingerprint, before);

function pieceFrame(overrides) {
    return Space.pieceFrame({
        placement_cm: { x: 10, y: 20, w: 60, h: 210, rotated: false },
        entry_pivot_mm: { x: 310, y: 1250 },
        pivot_mm: overrides.pivot || { x: 310, y: 1250 },
        rotation_deg: overrides.rotation || 0,
        flip_h: overrides.flipH || false,
        flip_v: overrides.flipV || false,
        source_rotated_dims: overrides.sourceRotated || false,
        sheet_no: overrides.sheet || 1,
    }, {
        1: { origin_x_mm: overrides.originX == null ? 500 : overrides.originX, origin_y_mm: overrides.originY == null ? 40 : overrides.originY, trim_x_mm: 0, trim_y_mm: 0 },
        2: { origin_x_mm: 1800, origin_y_mm: 90, trim_x_mm: 0, trim_y_mm: 0 },
    }, { widthMm: 600, lengthMm: 2100 });
}

function roundTrip(frame, x, y) {
    const world = Space.doorToWorld(frame, x, y);
    const door = Space.worldToDoor(frame, world.x, world.y);
    assert.ok(Math.abs(door.x - x) < 1e-6, `${door.x} != ${x}`);
    assert.ok(Math.abs(door.y - y) < 1e-6, `${door.y} != ${y}`);
    return world;
}

const plain = pieceFrame({});
const world350 = roundTrip(plain, 350, 0);
assert.ok(Math.abs(Space.lengthMm(roundTrip(plain, 0, 0).x, roundTrip(plain, 0, 0).y, world350.x, world350.y) - 350) < 1e-6);
roundTrip(pieceFrame({ rotation: 90 }), 350, 120);
roundTrip(pieceFrame({ rotation: 30 }), 350, 120);
roundTrip(pieceFrame({ flipH: true }), 350, 80);
roundTrip(pieceFrame({ flipV: true, rotation: 45 }), 40, 90);
roundTrip(pieceFrame({ sheet: 2, originX: 1800, originY: 90 }), 350, 0);
roundTrip(pieceFrame({ pivot: { x: 900, y: 400 }, rotation: 30 }), 350, 20);
roundTrip(pieceFrame({ sourceRotated: true }), 350, 120);

function visualEntry(point, piece, boards) {
    const entryPivot = piece.entry_pivot_mm;
    const worldPivot = editor.MoveGeometry.pivotInWorld(piece, boards);
    let x = point[0];
    let y = point[1];
    const angle = Number(piece.rotation_deg) || 0;
    if (angle) {
        const rotated = editor.RotationGeometry.rotatePoint([x, y], entryPivot, angle);
        x = rotated[0];
        y = rotated[1];
    }
    return {
        x: x - entryPivot.x + worldPivot.x,
        y: y - entryPivot.y + worldPivot.y,
    };
}

function alignedPiece(rotation, pivot) {
    return {
        placement_cm: { x: 10, y: 20, w: 60, h: 210, rotated: false },
        entry_pivot_mm: { x: 400, y: 1250 },
        pivot_mm: pivot || { x: 400, y: 1250 },
        rotation_deg: rotation || 0,
        flip_h: false,
        flip_v: false,
        sheet_no: 1,
    };
}

const alignedBoards = {
    1: { origin_x_mm: 500, origin_y_mm: 40, trim_x_mm: 0, trim_y_mm: 0 },
};
[0, 30, 90].forEach((rotation) => {
    const piece = alignedPiece(rotation, rotation === 30 ? { x: 560, y: 1400 } : { x: 400, y: 1250 });
    const frame = Space.pieceFrame(piece, alignedBoards, { widthMm: 600, lengthMm: 2100 });
    const doorOrigin = Space.doorToWorld(frame, 0, 0);
    const visualOrigin = visualEntry([100, 200], piece, alignedBoards);
    assert.ok(Math.abs(doorOrigin.x - visualOrigin.x) < 1e-6, `origin x ${rotation}`);
    assert.ok(Math.abs(doorOrigin.y - visualOrigin.y) < 1e-6, `origin y ${rotation}`);
    const click = { x: visualOrigin.x + 40, y: visualOrigin.y + 25 };
    const door = Space.worldToDoor(frame, click.x, click.y);
    const drawn = Space.doorToWorld(frame, door.x, door.y);
    assert.ok(Math.abs(drawn.x - click.x) < 1e-6, `click x ${rotation}`);
    assert.ok(Math.abs(drawn.y - click.y) < 1e-6, `click y ${rotation}`);
});

const outsideFrame = Space.pieceFrame(alignedPiece(15), alignedBoards, { widthMm: 600, lengthMm: 2100 });
const outsideWorld = Space.doorToWorld(outsideFrame, -80, 30);
const outsideDoor = Space.worldToDoor(outsideFrame, outsideWorld.x, outsideWorld.y);
assert.ok(Math.abs(outsideDoor.x + 80) < 1e-6);
assert.ok(Math.abs(outsideDoor.y - 30) < 1e-6);
assert.ok(outsideDoor.x < 0, "a click outside the blank stays outside; it is not a displaced door point");

const rotatedDown = Space.pieceFrame(alignedPiece(90), alignedBoards, { widthMm: 600, lengthMm: 2100 });
const down = Space.polarPoint({ x: 0, y: 0 }, 350, 90);
const downWorld = Space.doorToWorld(rotatedDown, down.x, down.y);
const downDoor = Space.worldToDoor(rotatedDown, downWorld.x, downWorld.y);
assert.ok(Math.abs(downDoor.x) < 1e-6);
assert.ok(Math.abs(downDoor.y - 350) < 1e-6);
const unrotatedDown = Space.doorToWorld(
    Space.pieceFrame(alignedPiece(0), alignedBoards, { widthMm: 600, lengthMm: 2100 }),
    down.x,
    down.y
);
assert.ok(Math.abs(downWorld.x - unrotatedDown.x) > 1 || Math.abs(downWorld.y - unrotatedDown.y) > 1);

[0.2, 4].forEach((scale) => {
    const camera = { scale, scrollX: 30, scrollY: 80, padX: 12, padY: 16, minX: -40, minY: -10 };
    const screen = Space.worldToScreen(world350, camera);
    const back = Space.screenToWorld(screen, camera);
    const door = Space.worldToDoor(plain, back.x, back.y);
    assert.ok(Math.abs(door.x - 350) < 1e-6);
    assert.ok(Math.abs(door.y) < 1e-6);
});

const endpoints = readySession();
endpoints.placePoint(0, 0);
endpoints.placePolar(200, 0);
endpoints.finish();
const snapped = Space.endpointSnap(endpoints.current().document.paths, { x: 3, y: 1 }, 8, null);
assert.equal(snapped.x, 0);
assert.equal(snapped.y, 0);
assert.equal(Space.endpointSnap(endpoints.current().document.paths, { x: 40, y: 40 }, Space.thresholdMm(2), null), null);

const page = fs.readFileSync(path.join(root, "almdina_erp/page/board_editor/board_editor.js"), "utf8");
const controller = fs.readFileSync(path.join(root, "public/js/board_editor/controller.js"), "utf8");
assert.match(page, /drawing_model\.js/);
assert.match(controller, /saveDrawing/);
assert.match(controller, /commitNumeric\(/);
assert.doesNotMatch(fs.readFileSync(path.join(root, "public/js/board_editor/drawing_model.js"), "utf8"), /distributionFingerprint|special_shape_geometry_json|snapshot_json/);

console.log("board editor polyline tests ok");
