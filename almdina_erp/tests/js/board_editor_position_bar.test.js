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
        "public/js/board_editor/alignment_geometry.js",
        "public/js/board_editor/store.js",
        "public/js/board_editor/canvas_renderer.js",
        "public/js/board_editor/right_sidebar_renderer.js",
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
assert.equal(PositionGeometry.AXES[0], "x");
assert.equal(PositionGeometry.AXES[1], "y");
assert.equal(PositionGeometry.AXES.length, 2);
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
// Usable-origin AABB: placement 10×20 mm inside usable area (trim is NOT added).
assert.equal(PositionGeometry.formatMm(modelA.x), "10");
assert.equal(PositionGeometry.formatMm(modelA.y), "20");
assert.equal(modelA.left, undefined);
assert.equal(modelA.top, undefined);

// Non-rect polygon uses transformed outline AABB in usable coords.
const modelPoly = PositionGeometry.boardPositionForPiece(session, keyPoly);
assert.ok(modelPoly);
assert.equal(PositionGeometry.formatMm(modelPoly.x), "600");
assert.equal(PositionGeometry.formatMm(modelPoly.y), "700");

function applyAxis(activeStore, pieceKey, axis, value) {
    const proposal = PositionGeometry.proposeAxisMove(activeStore.snapshot().session, pieceKey, axis, value);
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
        model: PositionGeometry.boardPositionForPiece(activeStore.snapshot().session, pieceKey),
    };
}

function applyNudge(activeStore, pieceKey, key) {
    const proposal = PositionGeometry.proposeKeyboardNudge(activeStore.snapshot().session, pieceKey, key);
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
        model: PositionGeometry.boardPositionForPiece(activeStore.snapshot().session, pieceKey),
    };
}

// X 10→12 moves piece +2 mm; Y unchanged.
{
    store.selectPiece(1, { pieceKey: keyA, sheetNo: 1, mode: "replace" });
    const before = PositionGeometry.boardPositionForPiece(store.snapshot().session, keyA);
    assert.equal(PositionGeometry.formatMm(before.x), "10");
    const result = applyAxis(store, keyA, "x", 12);
    assert.equal(result.ok, true);
    assert.equal(PositionGeometry.formatMm(result.model.x), "12");
    assert.equal(PositionGeometry.formatMm(result.model.y), PositionGeometry.formatMm(before.y));
    assert.equal(store.snapshot().canUndo, true);
}

// Unchanged value does not create history.
{
    const undoBefore = store.snapshot().canUndo;
    const result = applyAxis(store, keyA, "x", 12);
    assert.equal(result.ok, true);
    assert.equal(result.unchanged, true);
    assert.equal(store.snapshot().canUndo, undoBefore);
}

// Y +1 moves downward; X unchanged.
{
    const before = PositionGeometry.boardPositionForPiece(store.snapshot().session, keyA);
    const result = applyAxis(store, keyA, "y", before.y + 1);
    assert.equal(result.ok, true);
    assert.equal(PositionGeometry.formatMm(result.model.y), PositionGeometry.formatMm(before.y + 1));
    assert.equal(PositionGeometry.formatMm(result.model.x), PositionGeometry.formatMm(before.x));
}

// Decimal step via axis target.
{
    const before = PositionGeometry.boardPositionForPiece(store.snapshot().session, keyA);
    const result = applyAxis(store, keyA, "x", before.x + 0.5);
    assert.equal(result.ok, true);
    assert.equal(PositionGeometry.formatMm(result.model.x), PositionGeometry.formatMm(before.x + 0.5));
}

// Keyboard nudge: Right Right Down Up Left → net +1 X.
{
    const start = PositionGeometry.boardPositionForPiece(store.snapshot().session, keyA);
    assert.equal(applyNudge(store, keyA, "ArrowRight").ok, true);
    assert.equal(applyNudge(store, keyA, "ArrowRight").ok, true);
    assert.equal(applyNudge(store, keyA, "ArrowDown").ok, true);
    assert.equal(applyNudge(store, keyA, "ArrowUp").ok, true);
    assert.equal(applyNudge(store, keyA, "ArrowLeft").ok, true);
    const end = PositionGeometry.boardPositionForPiece(store.snapshot().session, keyA);
    assert.equal(PositionGeometry.formatMm(end.x), PositionGeometry.formatMm(start.x + 1));
    assert.equal(PositionGeometry.formatMm(end.y), PositionGeometry.formatMm(start.y));
}

// Reject move that leaves usable board; no partial change / no history entry.
{
    const before = JSON.stringify(store.snapshot().session.pieces[keyA]);
    const undoBefore = store.snapshot().canUndo;
    const result = applyAxis(store, keyA, "x", 900);
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
    assert.equal(applyAxis(local, keyA, "x", 400).ok, true);
    const before = JSON.stringify(local.snapshot().session.pieces[keyA]);
    const undoBefore = local.snapshot().canUndo;
    const collide = applyAxis(local, keyA, "y", 410);
    assert.equal(collide.ok, false, collide.reason || "expected overlap rejection");
    assert.equal(JSON.stringify(local.snapshot().session.pieces[keyA]), before);
    assert.equal(local.snapshot().canUndo, undoBefore);
    assert.ok(local.snapshot().dropMessage);
}

// Undo / redo restores X/Y.
{
    store.selectPiece(1, { pieceKey: keyA, sheetNo: 1, mode: "replace" });
    const start = PositionGeometry.boardPositionForPiece(store.snapshot().session, keyA);
    applyAxis(store, keyA, "y", start.y + 3);
    const moved = PositionGeometry.boardPositionForPiece(store.snapshot().session, keyA);
    assert.equal(PositionGeometry.formatMm(moved.y), PositionGeometry.formatMm(start.y + 3));
    store.undo();
    const undone = PositionGeometry.boardPositionForPiece(store.snapshot().session, keyA);
    assert.equal(PositionGeometry.formatMm(undone.y), PositionGeometry.formatMm(start.y));
    store.redo();
    const redone = PositionGeometry.boardPositionForPiece(store.snapshot().session, keyA);
    assert.equal(PositionGeometry.formatMm(redone.y), PositionGeometry.formatMm(moved.y));
}

// Rotation 45° recalculates X/Y from transformed outline AABB.
{
    const fresh = SessionDocument.buildFromProjection(projection, layout);
    const piece = fresh.pieces[keyA];
    const before = PositionGeometry.boardPositionForPiece(fresh, keyA);
    RotationGeometry.ensureBaseGeometry(piece);
    piece.rotation_deg = 45;
    RotationGeometry.rederiveOutline(piece);
    assert.equal(piece.rotation_deg, 45);
    const after = PositionGeometry.boardPositionForPiece(fresh, keyA);
    assert.ok(after);
    assert.notEqual(PositionGeometry.formatMm(after.x), PositionGeometry.formatMm(before.x));
    assert.notEqual(PositionGeometry.formatMm(after.y), PositionGeometry.formatMm(before.y));
    assert.equal(after.widthMm, 200);
    assert.equal(after.lengthMm, 100);
}

// Mirror + translate updates X while keeping source dims.
{
    const fresh = SessionDocument.buildFromProjection(projection, layout);
    const before = PositionGeometry.boardPositionForPiece(fresh, keyPoly);
    const piece = fresh.pieces[keyPoly];
    const outlineBefore = JSON.stringify(piece.outline_mm);
    const xs = (piece.outline_mm || []).map((point) => Number(point[0]) || 0);
    const mid = (Math.min(...xs) + Math.max(...xs)) * 0.5;
    piece.outline_mm = piece.outline_mm.map((point) => [2 * mid - Number(point[0]), Number(point[1])]);
    piece.base_outline_mm = (piece.base_outline_mm || []).map((point) => [2 * mid - Number(point[0]), Number(point[1])]);
    piece.outline_mm = piece.outline_mm.map((point) => [Number(point[0]) - 25, Number(point[1])]);
    piece.base_outline_mm = piece.base_outline_mm.map((point) => [Number(point[0]) - 25, Number(point[1])]);
    const after = PositionGeometry.boardPositionForPiece(fresh, keyPoly);
    assert.ok(after);
    assert.notEqual(JSON.stringify(piece.outline_mm), outlineBefore);
    assert.equal(after.widthMm, before.widthMm);
    assert.equal(after.lengthMm, before.lengthMm);
    assert.equal(PositionGeometry.formatMm(after.x), PositionGeometry.formatMm(before.x - 25));
}

// Delta helpers: typing alone does not mutate until propose/apply.
{
    const snap = store.snapshot().session;
    const pieceBefore = JSON.stringify(snap.pieces[keyA]);
    const current = PositionGeometry.boardPositionForPiece(snap, keyA);
    const delta = PositionGeometry.worldDeltaForAxis(current, "x", current.x + 5);
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

const rightSidebarSource = fs.readFileSync(
    path.join(root, "public/js/board_editor/right_sidebar_renderer.js"),
    "utf8"
);
assert.doesNotMatch(canvasSource, /data-abe-position-bar/);
assert.match(canvasSource, /abe-float-tools/);
assert.match(rightSidebarSource, /data-abe-position-bar/);
assert.match(rightSidebarSource, /abe-pos-input/);
assert.match(rightSidebarSource, /data-abe-pos-axis/);
assert.doesNotMatch(rightSidebarSource, /data-abe-pos-edge/);
assert.doesNotMatch(canvasSource, /Top inset|Bottom inset|Left inset|Right inset/);
assert.match(controllerSource, /applyPositionAxis/);
assert.match(controllerSource, /proposeAxisMove|proposeKeyboardNudge/);
assert.match(controllerSource, /nudgeSelectedPieceByArrow/);
assert.match(controllerSource, /PositionGeometry/);
assert.match(controllerSource, /RightSidebarRenderer/);
assert.doesNotMatch(controllerSource, /applyPositionEdge|proposeEdgeMove/);
assert.match(pageSource, /position_geometry\.js\?v=2/);
assert.match(pageSource, /right_sidebar_renderer\.js\?v=2/);
assert.match(pageSource, /board_editor\.css\?v=35/);
assert.match(cssSource, /\.abe-right-sidebar/);
assert.match(cssSource, /\.abe-pos-axis-label/);
assert.doesNotMatch(cssSource, /\.abe-right-sidebar\s*\{[^}]*grid-template-rows:\s*minmax\(0,\s*1fr\)\s+auto/);

[
    "Precision piece position",
    "X (mm)",
    "Y (mm)",
    "Decrease {0} by 1 mm",
    "Increase {0} by 1 mm",
    "Enter a valid millimetre value.",
    "Position update rejected.",
].forEach((messageId) => {
    assert.ok(arCsv.includes(messageId), `missing ar.csv key: ${messageId}`);
});

// Right inspector shows / hides X/Y with selection; canvas float bar stays tool-only.
function inspectorHostStub() {
    return {
        __html: "",
        set innerHTML(value) { this.__html = String(value); },
        get innerHTML() { return this.__html; },
        querySelector(selector) {
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

function renderInspector(keys) {
    const view = store.snapshot();
    view.selectedPieceKeys = keys.slice();
    view.selectedPieceKey = keys.length === 1 ? keys[0] : null;
    view.selectedPieceId = keys.length === 1
        ? Number((view.session.pieces[keys[0]] || {}).piece_id)
        : null;
    view.selectedSheetNo = keys.length === 1
        ? (view.session.pieces[keys[0]] && view.session.pieces[keys[0]].sheet_no)
        : null;
    const host = inspectorHostStub();
    editor.RightSidebarRenderer.render(host, view, {});
    return host.innerHTML;
}

{
    assert.ok(editor.RightSidebarRenderer);
    assert.equal(PositionGeometry.selectionPositionModel(store.snapshot().session, [keyA, keyB]), null);
    assert.equal(PositionGeometry.selectionPositionModel(store.snapshot().session, [keyOut]), null);
    const html = renderInspector([keyA]);
    assert.match(html, /data-abe-position-bar/);
    assert.match(html, /abe-pos-input/);
    assert.match(html, /data-abe-pos-axis="x"/);
    assert.match(html, /data-abe-pos-axis="y"/);
    assert.doesNotMatch(html, /data-abe-pos-edge/);
    assert.doesNotMatch(renderInspector([]), /data-abe-position-bar/);
    assert.match(renderInspector([]), /Select a piece to edit its properties/);
    assert.match(renderInspector([keyA, keyB]), /Multiple pieces selected/);
    assert.doesNotMatch(renderInspector([keyOut]), /data-abe-pos-axis/);
    assert.match(renderInspector([keyOut]), /Board X\/Y is available for pieces placed on a board/);
}

console.log("board_editor_position_bar.test.js: ok");
