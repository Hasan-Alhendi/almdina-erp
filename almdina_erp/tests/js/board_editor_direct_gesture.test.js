"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.resolve(__dirname, "../..");

function loadEditor() {
    const files = [
        "public/js/board_editor/history.js",
        "public/js/board_editor/session_document.js",
        "public/js/board_editor/move_geometry.js",
        "public/js/board_editor/move_interaction.js",
        "public/js/board_editor/store.js",
        "public/js/board_editor/canvas_renderer.js",
        "public/js/board_editor/controller.js",
        "public/js/board_editor/sidebar_renderer.js",
    ];
    const context = {
        frappe: { utils: { escape_html: (value) => String(value) } },
        __: (message) => message,
        console,
    };
    context.window = context;
    context.globalThis = context;
    vm.createContext(context);
    files.forEach((relativePath) => {
        vm.runInContext(fs.readFileSync(path.join(root, relativePath), "utf8"), context);
    });
    return context.window.AlmdinaBoardEditor;
}

const editor = loadEditor();
const {
    History,
    SessionDocument,
    MoveGeometry,
    createStore,
    createMoveInteraction,
    LONG_PRESS_MS,
    MOVE_THRESHOLD_PX,
} = editor;

assert.equal(LONG_PRESS_MS, 250);
assert.equal(MOVE_THRESHOLD_PX, 5);

const canvasSource = fs.readFileSync(path.join(root, "public/js/board_editor/canvas_renderer.js"), "utf8");
const controllerSource = fs.readFileSync(path.join(root, "public/js/board_editor/controller.js"), "utf8");
const sidebarSource = fs.readFileSync(path.join(root, "public/js/board_editor/sidebar_renderer.js"), "utf8");
assert.doesNotMatch(canvasSource, /abe-tool-select|abe-tool-move|data-abe-tool/);
assert.doesNotMatch(controllerSource, /setTool/);
assert.doesNotMatch(canvasSource, /long-press then drag to move/);
assert.match(canvasSource, /beginPieceGesture/);
assert.match(canvasSource, /abe-float-tools/);
assert.match(controllerSource, /onPanIntent|pagehide|blur/);
assert.match(sidebarSource, /data-layer-key|abe-piece-row/);
assert.doesNotMatch(sidebarSource, /beginPieceGesture|LONG_PRESS/);

const projection = {
    board: { kerf_cm: 0.4 },
    sheets: [
        {
            sheet_no: 1,
            full_width_cm: 100,
            full_length_cm: 100,
            applied_trim_width_cm: 0,
            applied_trim_length_cm: 0,
        },
        {
            sheet_no: 2,
            full_width_cm: 100,
            full_length_cm: 100,
            applied_trim_width_cm: 0,
            applied_trim_length_cm: 0,
        },
    ],
    pieces: [
        {
            piece_id: 1,
            piece_instance_id: "pi-a",
            label: "A",
            sheet_no: 1,
            placement_cm: { x: 10, y: 10, w: 20, h: 20 },
        },
        {
            piece_id: 2,
            piece_instance_id: "pi-host",
            label: "HOST",
            sheet_no: 1,
            placement_cm: { x: 40, y: 40, w: 30, h: 30 },
            glass_hole_local_mm: [[450, 450], [550, 450], [550, 550], [450, 550]],
        },
        {
            piece_id: 3,
            piece_instance_id: "pi-guest",
            label: "GUEST",
            sheet_no: 1,
            placement_cm: { x: 46, y: 46, w: 6, h: 6 },
            glass_host_piece_id: 2,
        },
        {
            piece_id: 4,
            piece_instance_id: "pi-locked",
            label: "LOCKED",
            sheet_no: 1,
            placement_cm: { x: 80, y: 80, w: 5, h: 5 },
        },
    ],
    elements: [
        {
            element_id: "e1",
            kind: "placement_rect",
            piece_id: 1,
            piece_instance_id: "pi-a",
            sheet_no: 1,
            payload: { placement_cm: { x: 10, y: 10, w: 20, h: 20 } },
        },
        {
            element_id: "e2",
            kind: "finished_outline",
            piece_id: 2,
            piece_instance_id: "pi-host",
            sheet_no: 1,
            geometry: { outer: [[400, 400], [700, 400], [700, 700], [400, 700]] },
        },
        {
            element_id: "e3",
            kind: "finished_outline",
            piece_id: 3,
            piece_instance_id: "pi-guest",
            sheet_no: 1,
            geometry: { outer: [[460, 460], [520, 460], [520, 520], [460, 520]] },
        },
        {
            element_id: "e4",
            kind: "unresolved",
            piece_id: 4,
            piece_instance_id: "pi-locked",
            sheet_no: 1,
            payload: {
                reason: "special_geometry_unavailable",
                placement_cm: { x: 80, y: 80, w: 5, h: 5 },
            },
        },
    ],
};

const layout = {
    positions: {
        1: { originX: 0, originY: 36, widthMm: 1000, heightMm: 1000, trimX: 0, trimY: 0 },
        2: { originX: 1100, originY: 36, widthMm: 1000, heightMm: 1000, trimX: 0, trimY: 0 },
    },
};

function makeHarness() {
    let now = 0;
    const timers = new Map();
    let nextTimerId = 1;
    const selections = [];
    const sheetSelections = [];
    const phases = [];
    const store = createStore({ projection, order_name: "O", plan_name: "P" });
    const session = SessionDocument.buildFromProjection(projection, layout);
    const history = History.create(session);
    store.attachSession(history.get(), history);

    const stage = {
        classList: {
            _set: new Set(),
            toggle(name, on) {
                if (on) this._set.add(name);
                else this._set.delete(name);
            },
            contains(name) {
                return this._set.has(name);
            },
            add(name) {
                this._set.add(name);
            },
            remove(name) {
                this._set.delete(name);
            },
        },
        style: { cursor: "" },
        scrollLeft: 0,
        scrollTop: 0,
        getBoundingClientRect: () => ({ left: 0, top: 0, right: 800, bottom: 600, width: 800, height: 600 }),
    };
    const svg = {
        getBoundingClientRect: () => ({ left: 0, top: 0, right: 800, bottom: 600, width: 800, height: 600 }),
    };
    const target = {
        setPointerCapture() {},
        releasePointerCapture() {},
    };

    const interaction = createMoveInteraction({
        store,
        getStageEl: () => stage,
        getSvgEl: () => svg,
        getWorldMetrics: () => ({ minX: 0, minY: 0, width: 2200, height: 1200 }),
        onPreview: () => {},
        onSelectPiece: (pieceId, elementId, pieceKey) => {
            selections.push({ pieceId, elementId, pieceKey });
            store.selectPiece(pieceId, { pieceKey, elementId });
        },
        onSelectSheet: (sheetNo) => {
            sheetSelections.push(sheetNo);
            store.selectSheet(sheetNo);
        },
        onGesturePhase: (phase) => phases.push(phase),
        isPanKey: () => false,
        now: () => now,
        setTimeout: (fn, ms) => {
            const id = nextTimerId;
            nextTimerId += 1;
            timers.set(id, { at: now + ms, fn });
            return id;
        },
        clearTimeout: (id) => {
            timers.delete(id);
        },
    });

    function advance(ms) {
        now += ms;
        const due = [...timers.entries()].filter(([, row]) => row.at <= now);
        due.sort((a, b) => a[1].at - b[1].at);
        due.forEach(([id, row]) => {
            timers.delete(id);
            row.fn();
        });
    }

    function pointer(type, clientX, clientY, pointerId) {
        return {
            type,
            button: 0,
            pointerId: pointerId == null ? 1 : pointerId,
            pointerType: "mouse",
            clientX,
            clientY,
            currentTarget: target,
            target,
            stopPropagation() {},
            preventDefault() {},
        };
    }

    return {
        store,
        history,
        interaction,
        selections,
        sheetSelections,
        phases,
        stage,
        advance,
        pointer,
        get now() {
            return now;
        },
        pendingTimers: () => timers.size,
    };
}

// Short click: select only, no history.
{
    const h = makeHarness();
    const before = h.history.state();
    h.interaction.beginPieceGesture("instance:pi-a", h.pointer("pointerdown", 120, 120), {
        pieceId: 1,
        elementId: "e1",
    });
    h.advance(40);
    h.interaction.onPointerUp(h.pointer("pointerup", 120, 120));
    assert.equal(h.interaction.getPhase(), "idle");
    assert.equal(h.selections.length, 1);
    assert.equal(Number(h.selections[0].pieceId), 1);
    assert.equal(h.history.state().canUndo, before.canUndo);
    assert.equal(h.store.snapshot().session.pieces["instance:pi-a"].local_x_mm, 100);
}

// Long-press then move: successful drag + one history command.
{
    const h = makeHarness();
    const startLocal = h.store.snapshot().session.pieces["instance:pi-a"].local_x_mm;
    h.interaction.beginPieceGesture("instance:pi-a", h.pointer("pointerdown", 100, 100), {
        pieceId: 1,
        elementId: "e1",
    });
    h.advance(LONG_PRESS_MS);
    assert.equal(h.interaction.getPhase(), "armed");
    assert.ok(h.stage.classList.contains("is-drag-armed"));
    h.interaction.onPointerMove(h.pointer("pointermove", 100 + MOVE_THRESHOLD_PX + 1, 100));
    assert.equal(h.interaction.getPhase(), "dragging");
    h.interaction.onPointerMove(h.pointer("pointermove", 160, 100));
    h.interaction.onPointerUp(h.pointer("pointerup", 160, 100));
    assert.equal(h.interaction.getPhase(), "idle");
    assert.ok(h.history.state().canUndo);
    assert.notEqual(h.store.snapshot().session.pieces["instance:pi-a"].local_x_mm, startLocal);
    assert.equal(h.store.snapshot().session.pieces["instance:pi-a"].piece_instance_id, "pi-a");
    assert.equal(h.selections.length, 0);
    assert.equal(h.interaction.consumeClickSuppression(), true);
}

// Early movement before long-press: no move, no late arm.
{
    const h = makeHarness();
    const start = h.store.snapshot().session.pieces["instance:pi-a"].local_x_mm;
    h.interaction.beginPieceGesture("instance:pi-a", h.pointer("pointerdown", 100, 100), {
        pieceId: 1,
        elementId: "e1",
    });
    h.interaction.onPointerMove(h.pointer("pointermove", 100 + MOVE_THRESHOLD_PX + 2, 100));
    assert.equal(h.interaction.getPhase(), "aborted");
    h.advance(LONG_PRESS_MS + 50);
    assert.equal(h.interaction.getPhase(), "aborted");
    h.interaction.onPointerMove(h.pointer("pointermove", 220, 100));
    h.interaction.onPointerUp(h.pointer("pointerup", 220, 100));
    assert.equal(h.store.snapshot().session.pieces["instance:pi-a"].local_x_mm, start);
    assert.equal(h.history.state().canUndo, false);
    assert.equal(h.selections.length, 1);
}

// Long-press without movement: no history.
{
    const h = makeHarness();
    h.interaction.beginPieceGesture("instance:pi-a", h.pointer("pointerdown", 100, 100), {
        pieceId: 1,
        elementId: "e1",
    });
    h.advance(LONG_PRESS_MS);
    assert.equal(h.interaction.getPhase(), "armed");
    h.interaction.onPointerUp(h.pointer("pointerup", 100, 100));
    assert.equal(h.history.state().canUndo, false);
    assert.equal(h.selections.length, 1);
}

// Release before long-press completes: timer cannot start a late drag.
{
    const h = makeHarness();
    h.interaction.beginPieceGesture("instance:pi-a", h.pointer("pointerdown", 100, 100), {
        pieceId: 1,
        elementId: "e1",
    });
    h.advance(LONG_PRESS_MS - 20);
    h.interaction.onPointerUp(h.pointer("pointerup", 100, 100));
    assert.equal(h.pendingTimers(), 0);
    assert.equal(h.interaction.getPhase(), "idle");
    h.advance(LONG_PRESS_MS);
    assert.equal(h.interaction.getPhase(), "idle");
    assert.equal(h.history.state().canUndo, false);
}

// Escape / pointercancel / page leave cancel incomplete gesture.
{
    const h = makeHarness();
    h.interaction.beginPieceGesture("instance:pi-a", h.pointer("pointerdown", 100, 100), {
        pieceId: 1,
        elementId: "e1",
    });
    h.advance(LONG_PRESS_MS);
    h.interaction.cancel();
    assert.equal(h.interaction.getPhase(), "idle");
    assert.equal(h.pendingTimers(), 0);
    assert.equal(h.history.state().canUndo, false);

    h.interaction.beginPieceGesture("instance:pi-a", h.pointer("pointerdown", 100, 100), {
        pieceId: 1,
        elementId: "e1",
    });
    h.interaction.onPointerCancel(h.pointer("pointercancel", 100, 100));
    assert.equal(h.interaction.getPhase(), "idle");
    assert.equal(h.pendingTimers(), 0);
}

// Pan intent cancels pending long-press without moving the piece.
{
    const h = makeHarness();
    const start = h.store.snapshot().session.pieces["instance:pi-a"].local_x_mm;
    h.interaction.beginPieceGesture("instance:pi-a", h.pointer("pointerdown", 100, 100), {
        pieceId: 1,
        elementId: "e1",
    });
    h.interaction.onPanIntent();
    assert.equal(h.interaction.getPhase(), "idle");
    h.advance(LONG_PRESS_MS + 10);
    assert.equal(h.store.snapshot().session.pieces["instance:pi-a"].local_x_mm, start);
}

// Locked/special piece: selectable, never arms drag.
{
    const h = makeHarness();
    h.interaction.beginPieceGesture("instance:pi-locked", h.pointer("pointerdown", 800, 800), {
        pieceId: 4,
        elementId: "e4",
    });
    h.advance(LONG_PRESS_MS + 10);
    assert.equal(h.interaction.getPhase(), "pending");
    h.interaction.onPointerMove(h.pointer("pointermove", 860, 800));
    h.interaction.onPointerUp(h.pointer("pointerup", 860, 800));
    assert.equal(h.history.state().canUndo, false);
    assert.equal(h.selections.length, 1);
    assert.equal(Number(h.selections[0].pieceId), 4);
}

// Board long-press drag keeps local piece coords; short click selects sheet.
{
    const h = makeHarness();
    h.interaction.beginBoardGesture(1, h.pointer("pointerdown", 10, 20));
    h.advance(40);
    h.interaction.onPointerUp(h.pointer("pointerup", 10, 20));
    assert.deepEqual(h.sheetSelections, [1]);

    const localBefore = h.store.snapshot().session.pieces["instance:pi-a"].local_x_mm;
    h.interaction.beginBoardGesture(1, h.pointer("pointerdown", 10, 20));
    h.advance(LONG_PRESS_MS);
    h.interaction.onPointerMove(h.pointer("pointermove", 10 + MOVE_THRESHOLD_PX + 1, 20));
    // Keep the board clear of sheet 2 (origin 1100) after the world-space delta.
    h.interaction.onPointerMove(h.pointer("pointermove", 40, 20));
    h.interaction.onPointerUp(h.pointer("pointerup", 40, 20));
    assert.ok(h.history.state().canUndo);
    assert.equal(h.store.snapshot().session.pieces["instance:pi-a"].local_x_mm, localBefore);
    assert.equal(h.store.snapshot().session.boards["1"].user_moved, true);
}

// Host drag moves guest once; undo/redo restore.
{
    const h = makeHarness();
    const guestBefore = h.store.snapshot().session.pieces["instance:pi-guest"].local_x_mm;
    h.interaction.beginPieceGesture("instance:pi-host", h.pointer("pointerdown", 420, 420), {
        pieceId: 2,
        elementId: "e2",
    });
    h.advance(LONG_PRESS_MS);
    h.interaction.onPointerMove(h.pointer("pointermove", 420 + MOVE_THRESHOLD_PX + 1, 420));
    h.interaction.onPointerMove(h.pointer("pointermove", 460, 420));
    h.interaction.onPointerUp(h.pointer("pointerup", 460, 420));
    const guestAfter = h.store.snapshot().session.pieces["instance:pi-guest"].local_x_mm;
    assert.notEqual(guestAfter, guestBefore);
    h.store.undo();
    assert.equal(h.store.snapshot().session.pieces["instance:pi-guest"].local_x_mm, guestBefore);
    h.store.redo();
    assert.equal(h.store.snapshot().session.pieces["instance:pi-guest"].local_x_mm, guestAfter);
}

console.log("board_editor_direct_gesture.test.js: ok");
