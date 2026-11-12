"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.resolve(__dirname, "../..");
const listeners = [];

function loadEditor() {
    const files = [
        "public/js/board_editor/editor_mode.js",
        "public/js/board_editor/history.js",
        "public/js/board_editor/session_document.js",
        "public/js/board_editor/move_geometry.js",
        "public/js/board_editor/rotation_geometry.js",
        "public/js/board_editor/measure_geometry.js",
        "public/js/board_editor/store.js",
        "public/js/board_editor/move_interaction.js",
        "public/js/board_editor/rotation_interaction.js",
        "public/js/board_editor/measure_interaction.js",
        "public/js/board_editor/canvas_renderer.js",
    ];
    const context = {
        frappe: { utils: { escape_html: (value) => String(value) } },
        __: (message) => message,
        console,
        addEventListener(type, fn, capture) {
            listeners.push({ type, fn, capture });
        },
        removeEventListener(type, fn) {
            const index = listeners.findIndex((row) => row.type === type && row.fn === fn);
            if (index >= 0) listeners.splice(index, 1);
        },
        setTimeout(fn) { return 1; },
        clearTimeout() {},
    };
    context.window = context;
    context.globalThis = context;
    vm.createContext(context);
    files.forEach((relative) => {
        vm.runInContext(fs.readFileSync(path.join(root, relative), "utf8"), context, { filename: relative });
    });
    return context.window.AlmdinaBoardEditor;
}

function piece(key, type) {
    return {
        piece_key: key,
        piece_id: type === "Special" ? 1 : 2,
        piece_instance_id: type === "Special" ? "piece:special" : "piece:regular",
        piece_type: type,
        label: type === "Special" ? "Special door" : "Regular door",
        sheet_no: 1,
        local_x_mm: 10,
        local_y_mm: 20,
        rotation_deg: 15,
        editable: true,
        distribution: "active",
        outline_mm: [[0, 0], [100, 0], [100, 50], [0, 50]],
    };
}

function session() {
    return {
        pieces: {
            special: piece("special", "Special"),
            regular: piece("regular", "Regular"),
        },
        boards: {
            1: { sheet_no: 1, origin_x_mm: 120, origin_y_mm: 36 },
        },
    };
}

function payload() {
    return {
        projection: {
            sheets: [],
            pieces: [
                {
                    piece_id: 1,
                    piece_instance_id: "piece:special",
                    piece_type: "Special",
                    original_w: 60,
                    original_h: 210,
                    label: "Special door",
                },
                {
                    piece_id: 2,
                    piece_instance_id: "piece:regular",
                    piece_type: "Regular",
                    original_w: 40,
                    original_h: 80,
                    label: "Regular door",
                },
            ],
        },
    };
}

function pointer(x, y) {
    return {
        pointerId: 7,
        button: 0,
        pointerType: "mouse",
        clientX: x,
        clientY: y,
        shiftKey: false,
        preventDefault() {},
        stopPropagation() {},
        currentTarget: {
            setPointerCapture() {},
            releasePointerCapture() {},
        },
        target: {},
    };
}

function svgStub() {
    return {
        getBoundingClientRect() {
            return { left: 0, top: 0, width: 1000, height: 800, right: 1000, bottom: 800 };
        },
        querySelector() { return null; },
        getAttribute() { return null; },
    };
}

function metrics() {
    return {
        width: 1000,
        height: 800,
        minX: 0,
        minY: 0,
        scale: 1,
        padX: 0,
        padY: 0,
        contentWidth: 1000,
        contentHeight: 800,
    };
}

const editor = loadEditor();
const { EditorMode, History, SessionDocument, createStore, createMoveInteraction, createRotationInteraction, createMeasureInteraction, CanvasRenderer } = editor;

assert.equal(EditorMode.normalize(undefined), "board");
assert.equal(EditorMode.normalize("drawing"), "drawing");
assert.equal(EditorMode.layoutCommandsAllowed("board"), true);
assert.equal(EditorMode.layoutCommandsAllowed("drawing"), false);
assert.equal(EditorMode.futureTools.every((tool) => tool.id && tool.labelKey), true);

const store = createStore(payload());
const history = History.create(session());
store.attachSession(session(), history);
store.noteDraftBaseline({ canSaveLayout: true, draftVersion: 2, savedFingerprint: "fp-layout" });
store.setViewport({
    scale: 2.4,
    scrollX: 320,
    scrollY: 140,
    padX: 18,
    padY: 24,
    opened: true,
    userAdjusted: true,
    cameraToken: 4,
});
const before = store.snapshot();
assert.equal(before.editorMode, "board");
assert.equal(before.drawingTarget.status, "board");
assert.equal(before.canUndo, false);

store.setEditorMode("drawing");
store.setEditorMode("drawing");
const drawing = store.snapshot();
assert.equal(drawing.editorMode, "drawing");
assert.equal(drawing.canUndo, false);
assert.equal(drawing.distributionDirty, before.distributionDirty);
assert.equal(drawing.savedFingerprint, "fp-layout");
assert.equal(JSON.stringify(drawing.session), JSON.stringify(before.session));
assert.equal(JSON.stringify(drawing.viewport), JSON.stringify(before.viewport));
assert.equal(SessionDocument.distributionFingerprint(drawing.session), SessionDocument.distributionFingerprint(before.session));
assert.equal(JSON.stringify(SessionDocument.exportLayout(drawing.session)).includes("editorMode"), false);

store.selectPiece(1, { pieceKey: "special", mode: "replace" });
const special = store.snapshot().drawingTarget;
assert.equal(special.status, "special");
assert.equal(special.pieceInstanceId, "piece:special");
assert.equal(special.label, "Special door");
assert.equal(special.widthCm, 60);
assert.equal(special.lengthCm, 210);
assert.equal(special.canEdit, true);
assert.equal(store.snapshot().session.pieces.special.local_x_mm, 10);
assert.equal(store.snapshot().session.pieces.special.rotation_deg, 15);

store.selectPiece(2, { pieceKey: "regular", mode: "replace" });
assert.equal(store.snapshot().drawingTarget.status, "regular");
assert.equal(store.snapshot().drawingTarget.canEdit, false);

store.selectPiece(null, { pieceKey: null });
assert.equal(store.snapshot().drawingTarget.status, "none");
store.selectPiece(1, { pieceKey: "special", mode: "replace" });
store.selectPiece(2, { pieceKey: "regular", mode: "toggle" });
assert.equal(store.snapshot().drawingTarget.status, "multiple");

store.noteDraftBaseline({ canSaveLayout: false, draftVersion: 2, savedFingerprint: "fp-layout" });
store.selectPiece(1, { pieceKey: "special", mode: "replace" });
const locked = store.snapshot().drawingTarget;
assert.equal(locked.status, "special");
assert.equal(locked.canEdit, false);
assert.equal(locked.messageKey, "Drawing edits stay unavailable while this layout is read-only.");

store.setEditorMode("board");
assert.equal(store.snapshot().editorMode, "board");
assert.equal(store.snapshot().drawingTarget.status, "board");
const reopened = createStore(payload());
assert.equal(reopened.snapshot().editorMode, "board");

const move = createMoveInteraction({
    store,
    getStageEl: () => null,
    getSvgEl: svgStub,
    getWorldMetrics: metrics,
    onSelectPiece() {},
});
store.setEditorMode("board");
assert.equal(move.beginPieceGesture("special", pointer(20, 20), { pieceId: 1 }), true);
move.onPointerMove(pointer(80, 20));
assert.equal(move.getPhase(), "dragging");
assert.ok(listeners.some((row) => row.type === "pointermove"));
store.setEditorMode("drawing");
move.onPointerMove(pointer(120, 20));
assert.equal(move.getPhase(), "idle");
assert.equal(listeners.length, 0);
assert.equal(store.snapshot().session.pieces.special.local_x_mm, 10);

assert.equal(move.beginPieceGesture("special", pointer(20, 20), { pieceId: 1 }), true);
move.onPointerMove(pointer(80, 30));
assert.notEqual(move.getPhase(), "dragging");
move.onPointerUp(pointer(80, 30));
assert.equal(move.getPhase(), "idle");
assert.equal(listeners.length, 0);
assert.equal(store.snapshot().session.pieces.special.local_x_mm, 10);

assert.equal(move.beginBoardGesture(1, pointer(30, 30)), true);
move.onPointerMove(pointer(90, 30));
assert.notEqual(move.getPhase(), "dragging");
move.cancel();
assert.equal(store.snapshot().session.boards[1].origin_x_mm, 120);

for (let index = 0; index < 4; index += 1) {
    move.beginPieceGesture("special", pointer(10, 10), { pieceId: 1 });
    move.cancel();
}
assert.equal(listeners.length, 0);

const rotation = createRotationInteraction({
    store,
    getStageEl: () => null,
    getSvgEl: svgStub,
    getWorldMetrics: metrics,
    getScale: () => 1,
    onCommitted() { throw new Error("rotation committed in drawing mode"); },
});
assert.equal(rotation.beginHandleGesture("special", pointer(40, 40)), false);
assert.equal(rotation.applyNumericAngle("special", 40), false);
assert.equal(store.snapshot().session.pieces.special.rotation_deg, 15);

const measure = createMeasureInteraction({
    store,
    getSvgEl: svgStub,
    getWorldMetrics: metrics,
    isMeasureToolActive: () => true,
});
assert.equal(measure.beginTool(pointer(50, 50)), false);

store.setEditorMode("board");
const host = {
    clientWidth: 900,
    clientHeight: 640,
    innerHTML: "",
    querySelector(selector) {
        if (selector === "[data-abe-stage]") {
            return {
                clientWidth: 900,
                clientHeight: 640,
                scrollLeft: 0,
                scrollTop: 0,
                classList: { add() {}, remove() {}, toggle() {} },
                style: {},
                addEventListener() {},
                setPointerCapture() {},
            };
        }
        return {
            onclick: null,
            addEventListener() {},
            querySelector() { return null; },
            querySelectorAll() { return []; },
            classList: { add() {}, remove() {}, toggle() {} },
            style: {},
            setAttribute() {},
            getAttribute() { return null; },
        };
    },
    querySelectorAll() { return []; },
};
const cameraBefore = JSON.stringify(store.snapshot().viewport);
CanvasRenderer.render(host, store.snapshot(), {});
assert.match(host.innerHTML, /data-abe-editor-mode="board"/);
assert.match(host.innerHTML, /aria-pressed="true"/);
assert.match(host.innerHTML, /abe-zoom-in/);
assert.match(host.innerHTML, /abe-zoom-out/);
assert.match(host.innerHTML, /abe-fit-all/);
assert.doesNotMatch(host.innerHTML, /data-abe-drawing-workspace/);
assert.equal(JSON.stringify(store.snapshot().viewport), cameraBefore);

store.setEditorMode("drawing");
store.selectPiece(1, { pieceKey: "special", mode: "replace" });
CanvasRenderer.render(host, store.snapshot(), {});
assert.match(host.innerHTML, /data-abe-editor-mode="drawing"[^>]*aria-pressed="true"/);
assert.match(host.innerHTML, /data-abe-drawing-workspace="1"/);
assert.match(host.innerHTML, /Special door/);
assert.match(host.innerHTML, /60 × 210 cm/);
assert.match(host.innerHTML, /aria-disabled="true"/);
assert.match(host.innerHTML, /Polyline/);
assert.doesNotMatch(host.innerHTML, /<button[^>]*abe-drawing-tool/);
assert.match(host.innerHTML, /abe-undo[^>]*disabled/);
assert.match(host.innerHTML, /abe-measure[^>]*disabled/);
assert.doesNotMatch(host.innerHTML, /abe-zoom-in[^>]*disabled/);
assert.equal(JSON.stringify(store.snapshot().viewport), cameraBefore);
assert.doesNotMatch(host.innerHTML, /abe-float-tools[\s\S]*abe-save\b/);
assert.doesNotMatch(host.innerHTML, /abe-float-tools[\s\S]*abe-review\b/);
assert.doesNotMatch(host.innerHTML, /abe-float-tools[\s\S]*abe-create-plan\b/);

const controller = fs.readFileSync(path.join(root, "public/js/board_editor/controller.js"), "utf8");
const page = fs.readFileSync(path.join(root, "almdina_erp/page/board_editor/board_editor.js"), "utf8");
assert.match(controller, /function setEditorMode/);
assert.match(controller, /finishActiveGesture\(\);\s*measureArmedBeforeDrawing = false/);
assert.match(controller, /layoutCommandsAllowed\(\)/);
assert.doesNotMatch(controller, /save_board_editor_drawing|drawing_json|get_board_editor_drawing/);
assert.match(page, /editor_mode\.js\?v=/);
assert.doesNotMatch(fs.readFileSync(path.join(root, "public/js/board_editor/editor_mode.js"), "utf8"), /import frappe|drawing_json/);

console.log("board editor mode tests ok");
