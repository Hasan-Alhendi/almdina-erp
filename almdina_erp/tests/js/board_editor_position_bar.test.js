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
        "public/js/board_editor/rotation_geometry.js",
        "public/js/board_editor/position_geometry.js",
        "public/js/board_editor/store.js",
        "public/js/board_editor/canvas_renderer.js",
    ];
    const context = {
        frappe: { utils: { escape_html: (value) => String(value) } },
        __: (message, replace) => {
            if (!Array.isArray(replace) || !replace.length) return message;
            return replace.reduce((text, value, index) => text.replace(`{${index}}`, String(value)), message);
        },
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
    PositionGeometry,
    MoveGeometry,
    RotationGeometry,
    createStore,
    History,
    SessionDocument,
    CanvasRenderer,
} = editor;

assert.ok(PositionGeometry);
assert.equal(PositionGeometry.STEP_MM, 1);
assert.equal(PositionGeometry.formatMm(12), "12");
assert.equal(PositionGeometry.formatMm(2.5), "2.5");
assert.equal(PositionGeometry.formatMm(2.500), "2.5");
assert.equal(PositionGeometry.parseMm("12"), 12);
assert.equal(PositionGeometry.parseMm("2,5"), 2.5);
assert.equal(PositionGeometry.parseMm("abc"), null);

const projection = {
    board: { kerf_cm: 0.4 },
    sheets: [
        {
            sheet_no: 1,
            full_width_cm: 100,
            full_length_cm: 100,
            applied_trim_width_cm: 1,
            applied_trim_length_cm: 1,
        },
    ],
    pieces: [
        {
            piece_id: 1,
            piece_instance_id: "pi-a",
            label: "A",
            sheet_no: 1,
            placement_cm: { x: 1, y: 2, w: 20, h: 10 },
        },
        {
            piece_id: 2,
            piece_instance_id: "pi-b",
            label: "B",
            sheet_no: 1,
            placement_cm: { x: 40, y: 40, w: 10, h: 10 },
        },
        {
            piece_id: 3,
            piece_instance_id: "pi-out",
            label: "OUT",
            sheet_no: null,
            placement_cm: { x: 0, y: 0, w: 5, h: 5 },
        },
        {
            piece_id: 4,
            piece_instance_id: "pi-poly",
            label: "L",
            sheet_no: 1,
            placement_cm: { x: 60, y: 70, w: 30, h: 20 },
        },
    ],
    elements: [
        {
            element_id: "e1",
            kind: "finished_outline",
            piece_id: 1,
            piece_instance_id: "pi-a",
            sheet_no: 1,
            geometry: { outer: [[10, 20], [210, 20], [210, 120], [10, 120]] },
            payload: { placement_cm: { x: 1, y: 2, w: 20, h: 10 } },
        },
        {
            element_id: "e2",
            kind: "finished_outline",
            piece_id: 2,
            piece_instance_id: "pi-b",
            sheet_no: 1,
            geometry: { outer: [[400, 400], [500, 400], [500, 500], [400, 500]] },
            payload: { placement_cm: { x: 40, y: 40, w: 10, h: 10 } },
        },
        {
            element_id: "e3",
            kind: "finished_outline",
            piece_id: 3,
            piece_instance_id: "pi-out",
            sheet_no: null,
            geometry: { outer: [[0, 0], [50, 0], [50, 50], [0, 50]] },
            payload: { placement_cm: { x: 0, y: 0, w: 5, h: 5 } },
        },
        {
            element_id: "e4",
            kind: "finished_outline",
            piece_id: 4,
            piece_instance_id: "pi-poly",
            sheet_no: 1,
            geometry: {
                outer: [
                    [600, 700],
                    [900, 700],
                    [900, 800],
                    [700, 800],
                    [700, 900],
                    [600, 900],
                ],
            },
            payload: { placement_cm: { x: 60, y: 70, w: 30, h: 20 } },
        },
    ],
};

const layout = CanvasRenderer.sheetLayout(projection.sheets, 1);
const session = SessionDocument.buildFromProjection(projection, layout);
const history = History.create(session);
const store = createStore({ projection, order_name: "O", plan_name: "P" });
store.attachSession(history.get(), history);

const keyA = "instance:pi-a";
const keyB = "instance:pi-b";
const keyOut = "instance:pi-out";
const keyPoly = "instance:pi-poly";

// Visibility model: single on-board piece only.
assert.equal(PositionGeometry.selectionPositionModel(session, []), null);
assert.equal(PositionGeometry.selectionPositionModel(session, [keyA, keyB]), null);
assert.equal(PositionGeometry.selectionPositionModel(session, [keyOut]), null);
const modelA = PositionGeometry.selectionPositionModel(session, [keyA]);
assert.ok(modelA);
assert.equal(modelA.pieceKey, keyA);
assert.equal(modelA.label, "A");
assert.equal(modelA.widthMm, 200);
assert.equal(modelA.lengthMm, 100);
// trim 10mm + local min (10,20) against full board 1000×1000
assert.equal(PositionGeometry.formatMm(modelA.left), "20");
assert.equal(PositionGeometry.formatMm(modelA.top), "30");
assert.equal(PositionGeometry.formatMm(modelA.right), "780");
assert.equal(PositionGeometry.formatMm(modelA.bottom), "870");

// Non-rect polygon uses transformed outline AABB.
const modelPoly = PositionGeometry.boardInsetsForPiece(session, keyPoly);
assert.ok(modelPoly);
assert.equal(PositionGeometry.formatMm(modelPoly.left), "610");
assert.equal(PositionGeometry.formatMm(modelPoly.top), "710");
assert.equal(PositionGeometry.formatMm(modelPoly.right), "90");
assert.equal(PositionGeometry.formatMm(modelPoly.bottom), "90");

function applyEdge(activeStore, pieceKey, edge, value) {
    const proposal = PositionGeometry.proposeEdgeMove(activeStore.snapshot().session, pieceKey, edge, value);
    if (!proposal.ok) {
        activeStore.setDropMessage(proposal.reason || "rejected");
        return proposal;
    }
    if (proposal.unchanged) return proposal;
    let next = activeStore.snapshot().session;
    proposal.commands.forEach((command) => {
        next = MoveGeometry.applyPieceMove(next, command);
    });
    activeStore.commitSession(next);
    activeStore.setDropMessage(null);
    return {
        ok: true,
        model: PositionGeometry.boardInsetsForPiece(activeStore.snapshot().session, pieceKey),
    };
}

// Left 20→22 moves piece +2 mm; Right decreases; Top/Bottom unchanged.
{
    store.selectPiece(1, { pieceKey: keyA, sheetNo: 1, mode: "replace" });
    const before = PositionGeometry.boardInsetsForPiece(store.snapshot().session, keyA);
    assert.equal(PositionGeometry.formatMm(before.left), "20");
    const result = applyEdge(store, keyA, "left", 22);
    assert.equal(result.ok, true);
    const after = result.model;
    assert.equal(PositionGeometry.formatMm(after.left), "22");
    assert.equal(PositionGeometry.formatMm(after.right), PositionGeometry.formatMm(before.right - 2));
    assert.equal(PositionGeometry.formatMm(after.top), PositionGeometry.formatMm(before.top));
    assert.equal(PositionGeometry.formatMm(after.bottom), PositionGeometry.formatMm(before.bottom));
    assert.equal(store.snapshot().canUndo, true);
}

// Unchanged value does not create history.
{
    const undoBefore = store.snapshot().canUndo;
    const historySizeBefore = history.state().canUndo;
    const result = applyEdge(store, keyA, "left", 22);
    assert.equal(result.ok, true);
    assert.equal(result.unchanged, true);
    assert.equal(store.snapshot().canUndo, undoBefore);
    assert.equal(history.state().canUndo, historySizeBefore);
}

// Right +1 moves leftward.
{
    const before = PositionGeometry.boardInsetsForPiece(store.snapshot().session, keyA);
    const result = applyEdge(store, keyA, "right", before.right + 1);
    assert.equal(result.ok, true);
    assert.equal(PositionGeometry.formatMm(result.model.right), PositionGeometry.formatMm(before.right + 1));
    assert.equal(PositionGeometry.formatMm(result.model.left), PositionGeometry.formatMm(before.left - 1));
}

// Reject move that leaves usable board; no partial change / no history entry.
{
    const before = JSON.stringify(store.snapshot().session.pieces[keyA]);
    const undoBefore = store.snapshot().canUndo;
    const result = applyEdge(store, keyA, "left", 900);
    assert.equal(result.ok, false);
    assert.equal(JSON.stringify(store.snapshot().session.pieces[keyA]), before);
    assert.equal(store.snapshot().canUndo, undoBefore);
    assert.ok(store.snapshot().dropMessage);
}

// Overlap / kerf rejection against neighbouring piece.
{
    const fresh = SessionDocument.buildFromProjection(projection, layout);
    const hist = History.create(fresh);
    const local = createStore({ projection, order_name: "O", plan_name: "P" });
    local.attachSession(hist.get(), hist);
    assert.equal(applyEdge(local, keyA, "left", 400).ok, true);
    const before = JSON.stringify(local.snapshot().session.pieces[keyA]);
    const undoBefore = local.snapshot().canUndo;
    // B occupies ~400..500 local on both axes; matching top drives A into B.
    const collide = applyEdge(local, keyA, "top", 410);
    assert.equal(collide.ok, false, collide.reason || "expected overlap rejection");
    assert.equal(JSON.stringify(local.snapshot().session.pieces[keyA]), before);
    assert.equal(local.snapshot().canUndo, undoBefore);
    assert.ok(local.snapshot().dropMessage);
}

// Undo / redo restores insets.
{
    store.selectPiece(1, { pieceKey: keyA, sheetNo: 1, mode: "replace" });
    const start = PositionGeometry.boardInsetsForPiece(store.snapshot().session, keyA);
    applyEdge(store, keyA, "top", start.top + 3);
    const moved = PositionGeometry.boardInsetsForPiece(store.snapshot().session, keyA);
    assert.equal(PositionGeometry.formatMm(moved.top), PositionGeometry.formatMm(start.top + 3));
    store.undo();
    const undone = PositionGeometry.boardInsetsForPiece(store.snapshot().session, keyA);
    assert.equal(PositionGeometry.formatMm(undone.top), PositionGeometry.formatMm(start.top));
    store.redo();
    const redone = PositionGeometry.boardInsetsForPiece(store.snapshot().session, keyA);
    assert.equal(PositionGeometry.formatMm(redone.top), PositionGeometry.formatMm(moved.top));
}

// Rotation 45° recalculates insets from transformed outline AABB.
{
    const fresh = SessionDocument.buildFromProjection(projection, layout);
    const piece = fresh.pieces[keyA];
    const before = PositionGeometry.boardInsetsForPiece(fresh, keyA);
    RotationGeometry.ensureBaseGeometry(piece);
    piece.rotation_deg = 45;
    RotationGeometry.rederiveOutline(piece);
    assert.equal(piece.rotation_deg, 45);
    const after = PositionGeometry.boardInsetsForPiece(fresh, keyA);
    assert.ok(after);
    assert.notEqual(PositionGeometry.formatMm(after.left), PositionGeometry.formatMm(before.left));
    assert.notEqual(PositionGeometry.formatMm(after.right), PositionGeometry.formatMm(before.right));
    // Original placement length/width stay as source dims.
    assert.equal(after.widthMm, 200);
    assert.equal(after.lengthMm, 100);
}

// Reflection of outline preserves source dims; AABB can stay while vertices flip.
{
    const fresh = SessionDocument.buildFromProjection(projection, layout);
    const before = PositionGeometry.boardInsetsForPiece(fresh, keyPoly);
    const piece = fresh.pieces[keyPoly];
    const outlineBefore = JSON.stringify(piece.outline_mm);
    const xs = (piece.outline_mm || []).map((point) => Number(point[0]) || 0);
    const mid = (Math.min(...xs) + Math.max(...xs)) * 0.5;
    piece.outline_mm = piece.outline_mm.map((point) => [2 * mid - Number(point[0]), Number(point[1])]);
    piece.base_outline_mm = (piece.base_outline_mm || []).map((point) => [2 * mid - Number(point[0]), Number(point[1])]);
    // Translate after mirror so the board insets must change.
    piece.outline_mm = piece.outline_mm.map((point) => [Number(point[0]) - 25, Number(point[1])]);
    piece.base_outline_mm = piece.base_outline_mm.map((point) => [Number(point[0]) - 25, Number(point[1])]);
    const after = PositionGeometry.boardInsetsForPiece(fresh, keyPoly);
    assert.ok(after);
    assert.notEqual(JSON.stringify(piece.outline_mm), outlineBefore);
    assert.equal(after.widthMm, before.widthMm);
    assert.equal(after.lengthMm, before.lengthMm);
    assert.equal(PositionGeometry.formatMm(after.left), PositionGeometry.formatMm(before.left - 25));
    assert.equal(PositionGeometry.formatMm(after.right), PositionGeometry.formatMm(before.right + 25));
}

// Delta helpers: typing alone does not mutate until propose/apply.
{
    const snap = store.snapshot().session;
    const pieceBefore = JSON.stringify(snap.pieces[keyA]);
    const current = PositionGeometry.boardInsetsForPiece(snap, keyA);
    const delta = PositionGeometry.worldDeltaForEdge(current, "left", current.left + 5);
    assert.equal(delta.ok, true);
    assert.equal(delta.dx, 5);
    assert.equal(delta.dy, 0);
    assert.equal(JSON.stringify(store.snapshot().session.pieces[keyA]), pieceBefore);
}

// Canvas wiring + i18n + asset bootstrap.
const canvasSource = fs.readFileSync(path.join(root, "public/js/board_editor/canvas_renderer.js"), "utf8");
const controllerSource = fs.readFileSync(path.join(root, "public/js/board_editor/controller.js"), "utf8");
const pageSource = fs.readFileSync(path.join(root, "almdina_erp/page/board_editor/board_editor.js"), "utf8");
const cssSource = fs.readFileSync(path.join(root, "public/css/board_editor.css"), "utf8");
const arCsv = fs.readFileSync(path.join(root, "translations/ar.csv"), "utf8");

assert.match(canvasSource, /data-abe-position-bar/);
assert.match(canvasSource, /bindPositionBar/);
assert.match(canvasSource, /abe-pos-input/);
assert.match(controllerSource, /applyPositionEdge/);
assert.match(controllerSource, /proposeEdgeMove/);
assert.match(controllerSource, /PositionGeometry/);
assert.doesNotMatch(controllerSource, /top_mm|left_mm|right_mm|bottom_mm/);
assert.match(pageSource, /position_geometry\.js\?v=1/);
assert.match(cssSource, /\.abe-position-bar/);
assert.match(cssSource, /\.abe-float-stack/);

[
    "Precision piece position",
    "Top inset",
    "Bottom inset",
    "Left inset",
    "Right inset",
    "Decrease {0} by 1 mm",
    "Increase {0} by 1 mm",
    "Enter a valid millimetre value.",
    "Position update rejected.",
].forEach((messageId) => {
    assert.ok(arCsv.includes(messageId), `missing ar.csv key: ${messageId}`);
});

// Render shows / hides bar with selection.
function hostStub() {
    return {
        __html: "",
        set innerHTML(value) { this.__html = String(value); },
        get innerHTML() { return this.__html; },
        querySelector(selector) {
            if (selector === "[data-abe-stage]") {
                return {
                    scrollLeft: 0,
                    scrollTop: 0,
                    classList: { add() {}, remove() {}, contains() { return false; }, toggle() {} },
                    style: {},
                    addEventListener() {},
                    getBoundingClientRect: () => ({ left: 0, top: 0, width: 800, height: 600 }),
                };
            }
            if (selector === ".abe-svg") {
                return {
                    addEventListener() {},
                    querySelectorAll: () => [],
                    getBoundingClientRect: () => ({ left: 0, top: 0, width: 800, height: 600 }),
                };
            }
            if (selector === ".abe-float-dock") {
                return { addEventListener() {} };
            }
            if (selector === "[data-abe-position-bar]") {
                if (!this.__html.includes("data-abe-position-bar")) return null;
                return {
                    querySelectorAll: () => [],
                    querySelector: () => null,
                };
            }
            return {
                onclick: null,
                addEventListener() {},
                classList: { add() {}, remove() {}, contains() { return false; } },
                style: {},
            };
        },
        querySelectorAll() { return []; },
    };
}

function renderWithSelection(keys) {
    const view = store.snapshot();
    view.selectedPieceKeys = keys.slice();
    view.selectedPieceKey = keys.length === 1 ? keys[0] : null;
    view.selectedPieceId = keys.length === 1
        ? Number((view.session.pieces[keys[0]] || {}).piece_id)
        : null;
    view.selectedSheetNo = keys.length === 1
        ? (view.session.pieces[keys[0]] && view.session.pieces[keys[0]].sheet_no)
        : null;
    view.viewport = { scale: 0.2, scrollX: 0, scrollY: 0, cameraToken: 1, opened: true };
    const host = hostStub();
    CanvasRenderer.render(host, view, {});
    return host.innerHTML;
}

{
    assert.equal(PositionGeometry.selectionPositionModel(store.snapshot().session, [keyA, keyB]), null);
    assert.equal(PositionGeometry.selectionPositionModel(store.snapshot().session, [keyOut]), null);
    assert.match(renderWithSelection([keyA]), /data-abe-position-bar/);
    assert.match(renderWithSelection([keyA]), /abe-pos-input/);
    assert.doesNotMatch(renderWithSelection([]), /data-abe-position-bar/);
    // Outside piece: clear single-key fallback ids so the bar stays hidden.
    const outsideHtml = (() => {
        const view = store.snapshot();
        view.selectedPieceKeys = [keyOut];
        view.selectedPieceKey = keyOut;
        view.selectedPieceId = Number(view.session.pieces[keyOut].piece_id);
        view.selectedSheetNo = null;
        view.viewport = { scale: 0.2, scrollX: 0, scrollY: 0, cameraToken: 1, opened: true };
        const host = hostStub();
        CanvasRenderer.render(host, view, {});
        return host.innerHTML;
    })();
    assert.doesNotMatch(outsideHtml, /data-abe-position-bar/);
}

console.log("board_editor_position_bar.test.js: ok");
