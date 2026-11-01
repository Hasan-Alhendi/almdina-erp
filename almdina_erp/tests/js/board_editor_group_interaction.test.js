"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.resolve(__dirname, "../..");

function load(files) {
    const context = {
        frappe: { utils: { escape_html: (value) => String(value) }, ui: { form: { on() {} } } },
        __: (message) => message,
        document: { createElementNS: () => ({ setAttribute() {}, style: {}, appendChild() {} }) },
    };
    context.window = context;
    context.globalThis = context;
    vm.createContext(context);
    files.forEach((relative) => {
        vm.runInContext(fs.readFileSync(path.join(root, relative), "utf8"), context);
    });
    return context.window.AlmdinaBoardEditor;
}

const editor = load([
    "public/js/board_editor/history.js",
    "public/js/board_editor/session_document.js",
    "public/js/board_editor/move_geometry.js",
    "public/js/board_editor/snap_geometry.js",
    "public/js/board_editor/rotation_geometry.js",
    "public/js/board_editor/move_interaction.js",
    "public/js/door_cutting_order/cutting_plan/door_cutting_order_edge_display.js",
    "public/js/board_editor/plan_display_style.js",
    "public/js/board_editor/plan_edge_marks.js",
    "public/js/board_editor/store.js",
    "public/js/board_editor/canvas_renderer.js",
    "public/js/board_editor/sidebar_renderer.js",
]);
const {
    CanvasRenderer,
    History,
    MoveGeometry,
    SessionDocument,
    SidebarRenderer,
    SnapGeometry,
    createStore,
    createMoveInteraction,
    LONG_PRESS_MS,
} = editor;

const { cameraPointToWorld, zoomAroundFocal, wheelZoomFactor, shouldZoomWheel, SCALE_MIN, SCALE_MAX } = CanvasRenderer;

function worldAt(camera, focal) {
    return cameraPointToWorld(camera.scrollX, camera.scrollY, focal.x, focal.y, camera.scale, 16);
}

const scrolled = { scale: 0.4, scrollX: 240, scrollY: 180, pad: 16 };
const focal = { x: 90, y: 70 };
const before = worldAt(scrolled, focal);
const zoomed = zoomAroundFocal(scrolled, focal, 1.25);
const after = cameraPointToWorld(zoomed.scrollX, zoomed.scrollY, focal.x, focal.y, zoomed.scale, 16);
assert.ok(Math.abs(before.x - after.x) < 1e-6, `world x ${before.x} -> ${after.x}`);
assert.ok(Math.abs(before.y - after.y) < 1e-6, `world y ${before.y} -> ${after.y}`);
assert.ok(zoomed.scrollX > 0 && zoomed.scrollY > 0);
function viewportOf(camera, world, minX, minY) {
    return {
        x: camera.pad + world.x * camera.scale - 2 * minX * camera.scale - camera.scrollX,
        y: camera.pad + world.y * camera.scale - 2 * minY * camera.scale - camera.scrollY,
    };
}
const shiftedMin = { x: -120, y: -40 };
const shiftedWorld = {
    x: before.x + 2 * shiftedMin.x,
    y: before.y + 2 * shiftedMin.y,
};
const shiftedBefore = viewportOf(scrolled, shiftedWorld, shiftedMin.x, shiftedMin.y);
const shiftedAfter = viewportOf(
    { scale: zoomed.scale, scrollX: zoomed.scrollX, scrollY: zoomed.scrollY, pad: 16 },
    shiftedWorld,
    shiftedMin.x,
    shiftedMin.y
);
assert.ok(Math.abs(shiftedBefore.x - focal.x) < 1e-6);
assert.ok(Math.abs(shiftedBefore.y - focal.y) < 1e-6);
assert.ok(Math.abs(shiftedAfter.x - focal.x) < 1e-6);
assert.ok(Math.abs(shiftedAfter.y - focal.y) < 1e-6);

const widened = { left: 280, top: 40 };
const collapsed = { left: 48, top: 40 };
const client = { x: 520, y: 260 };
function focalFor(stage) {
    return { x: client.x - stage.left, y: client.y - stage.top };
}
[widened, collapsed].forEach((stage) => {
    const point = focalFor(stage);
    const camera = { scale: 0.35, scrollX: 160, scrollY: 90, pad: 16 };
    const held = worldAt(camera, point);
    const next = zoomAroundFocal(camera, point, 0.8);
    const kept = cameraPointToWorld(next.scrollX, next.scrollY, point.x, point.y, next.scale, 16);
    assert.ok(Math.abs(held.x - kept.x) < 1e-6);
    assert.ok(Math.abs(held.y - kept.y) < 1e-6);
});
assert.notEqual(focalFor(widened).x, focalFor(collapsed).x);

const capped = zoomAroundFocal({ scale: 7.5, scrollX: 100, scrollY: 80, pad: 16 }, { x: 40, y: 30 }, 3);
assert.equal(capped.scale, SCALE_MAX);
const cappedWorld = cameraPointToWorld(capped.scrollX, capped.scrollY, 40, 30, capped.scale, 16);
const cappedBefore = worldAt({ scale: 7.5, scrollX: 100, scrollY: 80 }, { x: 40, y: 30 });
assert.ok(Math.abs(cappedWorld.x - cappedBefore.x) < 1e-6);
const floored = zoomAroundFocal({ scale: 0.03, scrollX: 40, scrollY: 20, pad: 16 }, { x: 20, y: 10 }, 0.2);
assert.equal(floored.scale, SCALE_MIN);
assert.equal(shouldZoomWheel({ ctrlKey: false, deltaY: -40 }), false);
assert.ok(wheelZoomFactor(-100, 0, 800) > 1);
assert.ok(wheelZoomFactor(100, 0, 800) < 1);
assert.ok(Math.abs(wheelZoomFactor(2, 1, 800) - wheelZoomFactor(32, 0, 800)) < 1e-9);

const projection = {
    board: { kerf_cm: 0.4 },
    layers: [{ match_key: "GEOMETRY", original_name: "GEOMETRY" }],
    sheets: [
        { sheet_no: 1, full_width_cm: 100, full_length_cm: 100, applied_trim_width_cm: 0, applied_trim_length_cm: 0, usable_width_cm: 100, usable_length_cm: 100 },
        { sheet_no: 2, full_width_cm: 100, full_length_cm: 100, applied_trim_width_cm: 0, applied_trim_length_cm: 0, usable_width_cm: 100, usable_length_cm: 100 },
    ],
    pieces: [
        { piece_id: 1, piece_instance_id: "pi-a", label: "A", sheet_no: 1, placement_cm: { x: 10, y: 10, w: 20, h: 20 }, allow_rotation: true, allow_rotation_proven: true },
        { piece_id: 2, piece_instance_id: "pi-b", label: "B", sheet_no: 2, placement_cm: { x: 15, y: 12, w: 18, h: 16 }, allow_rotation: true, allow_rotation_proven: true },
        { piece_id: 3, piece_instance_id: "pi-host", label: "HOST", sheet_no: 1, placement_cm: { x: 40, y: 40, w: 30, h: 30 }, glass_hole_local_mm: [[450, 450], [550, 450], [550, 550], [450, 550]] },
        { piece_id: 4, piece_instance_id: "pi-guest", label: "GUEST", sheet_no: 1, placement_cm: { x: 46, y: 46, w: 6, h: 6 }, glass_host_piece_id: 3 },
        { piece_id: 5, piece_instance_id: "pi-edge", label: "EDGE", sheet_no: 1, placement_cm: { x: 88, y: 10, w: 8, h: 8 } },
        { piece_id: 6, piece_instance_id: "pi-locked", label: "LOCKED", sheet_no: 1, placement_cm: { x: 2, y: 80, w: 8, h: 8 } },
    ],
    elements: [
        { element_id: "s1", kind: "sheet_outline", sheet_no: 1, layer_match_key: "SHEET", payload: { full_width_cm: 100, full_length_cm: 100, usable_width_cm: 100, usable_length_cm: 100 } },
        { element_id: "s2", kind: "sheet_outline", sheet_no: 2, layer_match_key: "SHEET", payload: { full_width_cm: 100, full_length_cm: 100, usable_width_cm: 100, usable_length_cm: 100 } },
        { element_id: "a", kind: "finished_outline", piece_id: 1, piece_instance_id: "pi-a", sheet_no: 1, layer_match_key: "GEOMETRY", geometry: { outer: [[100, 100], [300, 100], [300, 300], [100, 300]] } },
        { element_id: "b", kind: "finished_outline", piece_id: 2, piece_instance_id: "pi-b", sheet_no: 2, layer_match_key: "GEOMETRY", geometry: { outer: [[150, 120], [330, 120], [330, 280], [150, 280]] } },
        { element_id: "h", kind: "finished_outline", piece_id: 3, piece_instance_id: "pi-host", sheet_no: 1, layer_match_key: "GEOMETRY", geometry: { outer: [[400, 400], [700, 400], [700, 700], [400, 700]] } },
        { element_id: "g", kind: "finished_outline", piece_id: 4, piece_instance_id: "pi-guest", sheet_no: 1, layer_match_key: "GEOMETRY", geometry: { outer: [[460, 460], [520, 460], [520, 520], [460, 520]] } },
        { element_id: "e", kind: "finished_outline", piece_id: 5, piece_instance_id: "pi-edge", sheet_no: 1, layer_match_key: "GEOMETRY", geometry: { outer: [[880, 100], [960, 100], [960, 180], [880, 180]] } },
        { element_id: "l", kind: "unresolved", piece_id: 6, piece_instance_id: "pi-locked", sheet_no: 1, layer_match_key: "GEOMETRY", payload: { reason: "special_geometry_unavailable", placement_cm: { x: 2, y: 80, w: 8, h: 8 } } },
    ],
};
const layout = {
    positions: {
        1: { originX: 0, originY: 36, widthMm: 1000, heightMm: 1000, trimX: 0, trimY: 0 },
        2: { originX: 1200, originY: 36, widthMm: 1000, heightMm: 1000, trimX: 0, trimY: 0 },
    },
};
const session = SessionDocument.buildFromProjection(projection, layout);
const keyA = "instance:pi-a";
const keyB = "instance:pi-b";
const keyHost = "instance:pi-host";
const keyGuest = "instance:pi-guest";
const keyEdge = "instance:pi-edge";
const keyLocked = "instance:pi-locked";

const store = createStore({ projection });
const history = History.create(session);
store.attachSession(history.get(), history);
store.selectPiece(1, { pieceKey: keyA, mode: "replace" });
store.selectPiece(2, { pieceKey: keyB, mode: "toggle" });
assert.equal(JSON.stringify(store.snapshot().selectedPieceKeys), JSON.stringify([keyA, keyB]));
store.selectPiece(1, { pieceKey: keyA, mode: "toggle" });
assert.equal(JSON.stringify(store.snapshot().selectedPieceKeys), JSON.stringify([keyB]));
store.selectPiece(1, { pieceKey: keyA, mode: "replace" });
assert.equal(JSON.stringify(store.snapshot().selectedPieceKeys), JSON.stringify([keyA]));
store.selectPiece(null, { pieceKey: null });
assert.equal(store.snapshot().selectedPieceKeys.length, 0);

store.selectPiece(1, { pieceKey: keyA, mode: "replace" });
store.selectPiece(2, { pieceKey: keyB, mode: "toggle" });
const hostNode = {
    innerHTML: "",
    set innerHTML(value) { this.__html = String(value); },
    get innerHTML() { return this.__html; },
    querySelector() {
        return { scrollTop: 0, addEventListener() {}, setPointerCapture() {} };
    },
    querySelectorAll() { return []; },
};
SidebarRenderer.render(hostNode, store.snapshot(), {});
assert.equal((hostNode.innerHTML.match(/data-piece-key="instance:pi-a"[^>]*class="abe-piece-row is-selected"|class="abe-piece-row is-selected"[^>]*data-piece-key="instance:pi-a"/) || []).length >= 0, true);
assert.match(hostNode.innerHTML, /data-piece-key="instance:pi-a"[^>]*class="abe-piece-row is-selected"|class="abe-piece-row is-selected"[^>]*data-piece-key="instance:pi-a"/);
assert.match(hostNode.innerHTML, /data-piece-key="instance:pi-b"[^>]*class="abe-piece-row is-selected"|class="abe-piece-row is-selected"[^>]*data-piece-key="instance:pi-b"/);

function makeHost() {
    return {
        clientWidth: 1100,
        clientHeight: 760,
        style: {},
        __html: "",
        set innerHTML(value) { this.__html = String(value); },
        get innerHTML() { return this.__html; },
        querySelector() {
            return {
                clientWidth: 1100,
                clientHeight: 700,
                scrollLeft: 0,
                scrollTop: 0,
                classList: { add() {}, remove() {} },
                style: {},
                addEventListener() {},
                querySelector() { return null; },
                querySelectorAll() { return []; },
                getBoundingClientRect() { return { left: 0, top: 0, width: 1100, height: 700, right: 1100, bottom: 700 }; },
            };
        },
        querySelectorAll() { return []; },
    };
}
store.setViewport({ scale: 0.3, opened: true, userAdjusted: true, columns: 1, cameraToken: 1 });
const canvas = makeHost();
CanvasRenderer.render(canvas, store.snapshot(), {});
assert.equal((canvas.innerHTML.match(/data-abe-selection-chrome="1"/g) || []).length, 2);
assert.equal(canvas.innerHTML.includes("abe-rotate-handle"), false);
assert.match(canvas.innerHTML, /Select one piece to remove it/);
store.selectPiece(1, { pieceKey: keyA, mode: "replace" });
CanvasRenderer.render(canvas, store.snapshot(), {});
assert.equal((canvas.innerHTML.match(/data-abe-selection-chrome="1"/g) || []).length, 1);
assert.match(canvas.innerHTML, /abe-rotate-handle/);

const plan = MoveGeometry.groupMovePlan(session, [keyHost, keyGuest], keyGuest);
assert.equal(JSON.stringify(plan.roots), JSON.stringify([keyHost]));
assert.equal(plan.moving.filter((key) => String(key) === keyGuest).length, 1);
const hostBefore = MoveGeometry.pieceWorldOrigin(session, keyHost);
const guestBefore = MoveGeometry.pieceWorldOrigin(session, keyGuest);
const movedPair = MoveGeometry.proposeGroupMove(session, plan.roots, 20, 0);
assert.equal(movedPair.ok, true);
assert.equal(movedPair.commands.length, 1);
let paired = session;
movedPair.commands.forEach((command) => {
    paired = MoveGeometry.applyPieceMove(paired, command);
});
const hostAfter = MoveGeometry.pieceWorldOrigin(paired, keyHost);
const guestAfter = MoveGeometry.pieceWorldOrigin(paired, keyGuest);
assert.ok(Math.abs((hostAfter.x - hostBefore.x) - 20) < 0.01);
assert.ok(Math.abs((guestAfter.x - guestBefore.x) - 20) < 0.01);
assert.equal(paired.pieces[keyGuest].glass_host_key, keyHost);

const cross = MoveGeometry.groupMovePlan(session, [keyA, keyB], keyA);
const gapBefore = MoveGeometry.pieceWorldOrigin(session, keyB).x - MoveGeometry.pieceWorldOrigin(session, keyA).x;
const crossMove = MoveGeometry.proposeGroupMove(session, cross.roots, 30, 12);
assert.equal(crossMove.ok, true);
let crossed = session;
crossMove.commands.forEach((command) => {
    crossed = MoveGeometry.applyPieceMove(crossed, command);
});
const gapAfter = MoveGeometry.pieceWorldOrigin(crossed, keyB).x - MoveGeometry.pieceWorldOrigin(crossed, keyA).x;
assert.ok(Math.abs(gapBefore - gapAfter) < 0.01);
assert.equal(crossed.pieces[keyA].piece_instance_id, "pi-a");
assert.equal(crossed.pieces[keyB].sheet_no, 2);

const blocked = MoveGeometry.proposeGroupMove(session, [keyA, keyEdge], 80, 0);
assert.equal(blocked.ok, false);
assert.equal(session.pieces[keyA].local_x_mm, SessionDocument.buildFromProjection(projection, layout).pieces[keyA].local_x_mm);

const originA = MoveGeometry.pieceWorldOrigin(session, keyA);
const snap = SnapGeometry.suggestPieceSnap(session, keyA, originA.x + 80, originA.y, {
    thresholdMm: 30,
    magnetEnabled: true,
    ignoreKeys: [keyB],
});
assert.equal(snap.ok, true);
assert.equal(String(snap.source || "").includes("pi-b"), false);
assert.equal(String(snap.source || "").includes(keyGuest), false);
const snapped = MoveGeometry.proposeGroupMove(session, [keyA, keyB], snap.dx, snap.dy);
assert.equal(snapped.ok, true);
let magnetized = session;
snapped.commands.forEach((command) => {
    magnetized = MoveGeometry.applyPieceMove(magnetized, command);
});
const magnetGap = MoveGeometry.pieceWorldOrigin(magnetized, keyB).x - MoveGeometry.pieceWorldOrigin(magnetized, keyA).x;
assert.ok(Math.abs(magnetGap - gapBefore) < 0.01);
const leaderOnly = MoveGeometry.proposeGroupMove(session, [keyA], snap.dx, snap.dy);
const withEdge = MoveGeometry.proposeGroupMove(session, [keyA, keyEdge], snap.dx, snap.dy);
assert.equal(leaderOnly.ok, true);
assert.equal(withEdge.ok, false);
const usedDx = withEdge.ok ? snap.dx : 80;
assert.notEqual(usedDx, snap.dx);

const groupHistory = History.create(session);
const committed = groupHistory.commit(crossed);
assert.equal(groupHistory.state().canUndo, true);
const undone = groupHistory.undo();
assert.ok(Math.abs(MoveGeometry.pieceWorldOrigin(undone, keyA).x - MoveGeometry.pieceWorldOrigin(session, keyA).x) < 0.01);
assert.ok(Math.abs(MoveGeometry.pieceWorldOrigin(undone, keyB).x - MoveGeometry.pieceWorldOrigin(session, keyB).x) < 0.01);
assert.equal(committed.pieces[keyA].piece_key, keyA);

let now = 0;
const timers = new Map();
let timerId = 1;
const selections = [];
const dragStore = createStore({ projection });
const dragHistory = History.create(SessionDocument.buildFromProjection(projection, layout));
dragStore.attachSession(dragHistory.get(), dragHistory);
dragStore.selectPiece(1, { pieceKey: keyA, mode: "replace" });
dragStore.selectPiece(2, { pieceKey: keyB, mode: "toggle" });
const interaction = createMoveInteraction({
    store: dragStore,
    getStageEl: () => ({
        classList: { toggle() {}, contains() { return false; }, add() {}, remove() {} },
        style: {},
        getBoundingClientRect: () => ({ left: 0, top: 0, right: 400, bottom: 300, width: 400, height: 300 }),
        scrollLeft: 0,
        scrollTop: 0,
    }),
    getSvgEl: () => ({ getBoundingClientRect: () => ({ left: 0, top: 0, width: 1000, height: 800 }) }),
    getWorldMetrics: () => ({ minX: 0, minY: 0, width: 1000, height: 800, scale: 1 }),
    onSelectPiece: (pieceId, elementId, pieceKey, meta) => selections.push({ pieceId, pieceKey, shiftKey: meta && meta.shiftKey }),
    getScale: () => 1,
    now: () => now,
    setTimeout: (fn, ms) => {
        const id = timerId;
        timerId += 1;
        timers.set(id, { fn, at: now + ms });
        return id;
    },
    clearTimeout: (id) => timers.delete(id),
});
function advance(ms) {
    now += ms;
    Array.from(timers.entries()).forEach(([id, timer]) => {
        if (timer.at <= now) {
            timers.delete(id);
            timer.fn();
        }
    });
}
function pointer(type, x, y, extra) {
    return { type, pointerId: 1, button: 0, clientX: x, clientY: y, pointerType: "mouse", shiftKey: false, preventDefault() {}, stopPropagation() {}, ...(extra || {}) };
}
const keysAtDown = dragStore.snapshot().selectedPieceKeys.slice();
interaction.beginPieceGesture(keyA, pointer("pointerdown", 40, 40), { pieceId: 1 });
assert.equal(JSON.stringify(dragStore.snapshot().selectedPieceKeys), JSON.stringify(keysAtDown));
advance(LONG_PRESS_MS);
interaction.onPointerMove(pointer("pointermove", 48, 40));
interaction.cancel();
assert.equal(dragStore.snapshot().dragPreview, null);
assert.equal(dragStore.snapshot().session.pieces[keyA].local_x_mm, session.pieces[keyA].local_x_mm);
interaction.beginPieceGesture(keyA, pointer("pointerdown", 40, 40), { pieceId: 1 });
interaction.onPointerUp(pointer("pointerup", 40, 40, { shiftKey: true }));
assert.equal(selections[selections.length - 1].shiftKey, true);
assert.equal(dragStore.snapshot().canUndo, false);

const lockedPlan = MoveGeometry.groupMovePlan(session, [keyA, keyLocked], keyA);
assert.equal(lockedPlan.locked, true);

const magnet = createMoveInteraction({
    store: dragStore,
    getStageEl: () => ({
        classList: { toggle() {}, contains() { return false; }, add() {}, remove() {} },
        style: {},
        getBoundingClientRect: () => ({ left: 0, top: 0, right: 400, bottom: 300, width: 400, height: 300 }),
        scrollLeft: 0,
        scrollTop: 0,
    }),
    getSvgEl: () => ({ getBoundingClientRect: () => ({ left: 0, top: 0, width: 1000, height: 800 }) }),
    getWorldMetrics: () => ({ minX: 0, minY: 0, width: 1000, height: 800, scale: 0.05 }),
    getScale: () => 0.05,
    now: () => now,
    setTimeout: (fn, ms) => {
        const id = timerId;
        timerId += 1;
        timers.set(id, { fn, at: now + ms });
        return id;
    },
    clearTimeout: (id) => timers.delete(id),
});
const sessionBeforeMagnet = dragStore.snapshot().session;
const gestureGap = MoveGeometry.pieceWorldOrigin(sessionBeforeMagnet, keyB).x
    - MoveGeometry.pieceWorldOrigin(sessionBeforeMagnet, keyA).x;
magnet.beginPieceGesture(keyA, pointer("pointerdown", 100, 160, { pointerId: 2 }), { pieceId: 1 });
assert.equal(JSON.stringify(dragStore.snapshot().selectedPieceKeys), JSON.stringify([keyA, keyB]));
advance(LONG_PRESS_MS);
magnet.onPointerMove(pointer("pointermove", 108, 160, { pointerId: 2 }));
magnet.onPointerMove(pointer("pointermove", 188, 160, { pointerId: 2 }));
const magnetPreview = dragStore.snapshot().dragPreview;
assert.equal(magnetPreview && magnetPreview.snapped, true);
assert.ok(magnetPreview.ids.length >= 2);
assert.equal(dragStore.snapshot().session.pieces[keyA].local_x_mm, sessionBeforeMagnet.pieces[keyA].local_x_mm);
magnet.onPointerUp(pointer("pointerup", 188, 160, { pointerId: 2 }));
assert.equal(dragStore.snapshot().dragPreview, null);
assert.equal(dragStore.snapshot().canUndo, true);
const magnetizedSession = dragStore.snapshot().session;
const magnetGapAfter = MoveGeometry.pieceWorldOrigin(magnetizedSession, keyB).x
    - MoveGeometry.pieceWorldOrigin(magnetizedSession, keyA).x;
assert.ok(Math.abs(magnetGapAfter - gestureGap) < 0.01);
dragStore.undo();
assert.equal(dragStore.snapshot().canUndo, false);
assert.equal(dragStore.snapshot().session.pieces[keyA].local_x_mm, sessionBeforeMagnet.pieces[keyA].local_x_mm);
assert.equal(dragStore.snapshot().session.pieces[keyB].local_x_mm, sessionBeforeMagnet.pieces[keyB].local_x_mm);
assert.equal(dragStore.snapshot().dragPreview, null);

const controllerSource = fs.readFileSync(path.join(root, "public/js/board_editor/controller.js"), "utf8");
assert.match(controllerSource, /wheel/);
assert.match(controllerSource, /passive:\s*false/);
assert.match(controllerSource, /zoomAroundFocal/);

console.log("board editor group interaction ok");
