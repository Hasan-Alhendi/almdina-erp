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

// Visibility model: single absolute; multi Mixed (same board eligible).
assert.equal(PositionGeometry.selectionPositionModel(session, []), null);
assert.equal(PositionGeometry.selectionPositionModel(session, [keyOut]), null);
const usableH = PositionGeometry.usableHeightMm(session.boards["1"]);
assert.equal(usableH, 980);
assert.equal(
    PositionGeometry.internalYToDisplayedY(980, { y: 20, h: 100 }),
    860
);
assert.equal(PositionGeometry.displayedYDeltaToInternal(860, 100), 760);

const modelA = PositionGeometry.selectionPositionModel(session, [keyA]);
assert.ok(modelA);
assert.equal(modelA.pieceKey, keyA);
assert.equal(modelA.mixed, false);
assert.equal(modelA.label, "A");
assert.equal(modelA.widthMm, 200);
assert.equal(modelA.lengthMm, 100);
// Bottom-left usable origin: X from left, Y from bottom (trim is NOT double-counted).
assert.equal(PositionGeometry.formatMm(modelA.x), "10");
assert.equal(PositionGeometry.formatMm(modelA.y), "860");
assert.equal(modelA.usableHeightMm, 980);
assert.equal(modelA.left, undefined);
assert.equal(modelA.top, undefined);

const mixedAB = PositionGeometry.selectionPositionModel(session, [keyA, keyB]);
assert.ok(mixedAB);
assert.equal(mixedAB.mixed, true);
assert.equal(mixedAB.editable, true);
assert.equal(mixedAB.displayX, PositionGeometry.MIXED_LABEL);
assert.equal(mixedAB.displayY, PositionGeometry.MIXED_LABEL);
assert.equal(mixedAB.x, null);
assert.equal(mixedAB.y, null);

// Non-rect polygon uses transformed outline AABB; Y is distance from usable bottom.
const modelPoly = PositionGeometry.boardPositionForPiece(session, keyPoly);
assert.ok(modelPoly);
assert.equal(PositionGeometry.formatMm(modelPoly.x), "600");
assert.equal(PositionGeometry.formatMm(modelPoly.y), "80");

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

function applyGroupStep(activeStore, keys, axis, stepMm) {
    const proposal = PositionGeometry.proposeGroupAxisStep(
        activeStore.snapshot().session,
        keys,
        axis,
        stepMm
    );
    if (!proposal.ok) {
        activeStore.setDropMessage(proposal.reason || "rejected");
        return proposal;
    }
    if (proposal.unchanged) {
        return {
            ok: true,
            unchanged: true,
            model: PositionGeometry.selectionPositionModel(activeStore.snapshot().session, keys),
        };
    }
    let next = activeStore.snapshot().session;
    proposal.commands.forEach((command) => {
        next = MoveGeometry.applyPieceMove(next, command);
    });
    activeStore.commitSession(next);
    activeStore.setDropMessage(null);
    return {
        ok: true,
        model: PositionGeometry.selectionPositionModel(activeStore.snapshot().session, keys),
        commands: proposal.commands,
    };
}

function applyGroupRelative(activeStore, keys, axis, textOrNumber) {
    const proposal = PositionGeometry.proposeGroupAxisRelative(
        activeStore.snapshot().session,
        keys,
        axis,
        textOrNumber
    );
    if (!proposal.ok) {
        activeStore.setDropMessage(proposal.reason || "rejected");
        return proposal;
    }
    if (proposal.unchanged) {
        return {
            ok: true,
            unchanged: true,
            model: PositionGeometry.selectionPositionModel(activeStore.snapshot().session, keys),
        };
    }
    let next = activeStore.snapshot().session;
    proposal.commands.forEach((command) => {
        next = MoveGeometry.applyPieceMove(next, command);
    });
    activeStore.commitSession(next);
    activeStore.setDropMessage(null);
    return {
        ok: true,
        model: PositionGeometry.selectionPositionModel(activeStore.snapshot().session, keys),
    };
}

function applyGroupNudge(activeStore, keys, key) {
    const proposal = PositionGeometry.proposeSelectionKeyboardNudge(
        activeStore.snapshot().session,
        keys,
        key
    );
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
        model: PositionGeometry.selectionPositionModel(activeStore.snapshot().session, keys),
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

// Y +1 moves upward (displayed Y increases); X unchanged.
{
    const before = PositionGeometry.boardPositionForPiece(store.snapshot().session, keyA);
    const fpBefore = MoveGeometry.footprint(store.snapshot().session.pieces[keyA]).bounds;
    const result = applyAxis(store, keyA, "y", before.y + 1);
    assert.equal(result.ok, true);
    assert.equal(PositionGeometry.formatMm(result.model.y), PositionGeometry.formatMm(before.y + 1));
    assert.equal(PositionGeometry.formatMm(result.model.x), PositionGeometry.formatMm(before.x));
    const fpAfter = MoveGeometry.footprint(store.snapshot().session.pieces[keyA]).bounds;
    assert.equal(PositionGeometry.formatMm(fpAfter.y), PositionGeometry.formatMm(fpBefore.y - 1));
}

// Y = 0 seats the AABB bottom on the usable bottom edge when valid.
{
    const fresh = SessionDocument.buildFromProjection(projection, layout);
    const hist = History.create(fresh);
    const local = createStore({ projection, order_name: "O", plan_name: "P" });
    local.attachSession(hist.get(), hist);
    const result = applyAxis(local, keyA, "y", 0);
    assert.equal(result.ok, true);
    assert.equal(PositionGeometry.formatMm(result.model.y), "0");
    const fp = MoveGeometry.footprint(local.snapshot().session.pieces[keyA]).bounds;
    assert.equal(PositionGeometry.formatMm(fp.y + fp.h), PositionGeometry.formatMm(usableH));
}

// Decimal step via axis target.
{
    const before = PositionGeometry.boardPositionForPiece(store.snapshot().session, keyA);
    const result = applyAxis(store, keyA, "x", before.x + 0.5);
    assert.equal(result.ok, true);
    assert.equal(PositionGeometry.formatMm(result.model.x), PositionGeometry.formatMm(before.x + 0.5));
}

// Keyboard nudge: screen arrows unchanged; ArrowUp raises displayed Y.
{
    const start = PositionGeometry.boardPositionForPiece(store.snapshot().session, keyA);
    assert.equal(applyNudge(store, keyA, "ArrowRight").ok, true);
    assert.equal(applyNudge(store, keyA, "ArrowRight").ok, true);
    assert.equal(applyNudge(store, keyA, "ArrowDown").ok, true);
    const afterDown = PositionGeometry.boardPositionForPiece(store.snapshot().session, keyA);
    assert.equal(PositionGeometry.formatMm(afterDown.y), PositionGeometry.formatMm(start.y - 1));
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
    // B sits at internal y=400 (displayed 480). Move A so its AABB overlaps B.
    const before = JSON.stringify(local.snapshot().session.pieces[keyA]);
    const undoBefore = local.snapshot().canUndo;
    const collide = applyAxis(local, keyA, "y", 480);
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
    // Displayed Y+ maps to internal dy negative (up).
    const deltaY = PositionGeometry.worldDeltaForAxis(current, "y", current.y + 5);
    assert.equal(deltaY.ok, true);
    assert.equal(deltaY.dx, 0);
    assert.equal(deltaY.dy, -5);
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
assert.match(pageSource, /position_geometry\.js\?v=4/);
assert.match(pageSource, /right_sidebar_renderer\.js\?v=4/);
assert.match(pageSource, /controller\.js\?v=33/);
assert.match(pageSource, /board_editor\.css\?v=36/);
assert.match(cssSource, /\.abe-right-sidebar/);
assert.match(cssSource, /\.abe-pos-axis-label/);
assert.doesNotMatch(cssSource, /\.abe-right-sidebar\s*\{[^}]*grid-template-rows:\s*minmax\(0,\s*1fr\)\s+auto/);
assert.match(controllerSource, /proposeGroupAxisStep|proposeGroupAxisRelative/);
assert.match(controllerSource, /proposeSelectionKeyboardNudge/);
assert.match(rightSidebarSource, /data-abe-pos-mixed/);
assert.match(rightSidebarSource, /parseRelativeOffset/);

[
    "Precision piece position",
    "X (mm)",
    "Y (mm)",
    "Decrease {0} by 1 mm",
    "Increase {0} by 1 mm",
    "Enter a valid millimetre value.",
    "Enter a valid millimetre offset.",
    "Position update rejected.",
    "Precise group moves are available for pieces on the same board only, or pieces outside all boards.",
    "Nudge selected pieces −1 mm on {0}",
    "Nudge selected pieces +1 mm on {0}",
    "Enter a relative millimetre offset for the selection (for example +5 or -2.5). Bare numbers mean a positive offset.",
].forEach((messageId) => {
    assert.ok(arCsv.includes(messageId), `missing ar.csv key: ${messageId}`);
});
assert.ok(arCsv.includes("Mixed"), "missing Mixed translation");

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
    assert.equal(PositionGeometry.selectionPositionModel(store.snapshot().session, [keyOut]), null);
    const html = renderInspector([keyA]);
    assert.match(html, /data-abe-position-bar/);
    assert.match(html, /abe-pos-input/);
    assert.match(html, /data-abe-pos-axis="x"/);
    assert.match(html, /data-abe-pos-axis="y"/);
    assert.doesNotMatch(html, /data-abe-pos-edge/);
    assert.doesNotMatch(html, /data-abe-pos-mixed/);
    assert.doesNotMatch(renderInspector([]), /data-abe-position-bar/);
    assert.match(renderInspector([]), /Select a piece to edit its properties/);
    const multiHtml = renderInspector([keyA, keyB]);
    assert.match(multiHtml, /data-abe-position-bar/);
    assert.match(multiHtml, /data-abe-pos-mixed/);
    assert.match(multiHtml, /2 pieces selected/);
    assert.match(multiHtml, /value="Mixed"/);
    assert.match(multiHtml, /data-abe-pos-step="-1"/);
    assert.match(multiHtml, /data-abe-pos-step="1"/);
    assert.doesNotMatch(renderInspector([keyOut]), /data-abe-pos-axis/);
    assert.match(renderInspector([keyOut]), /Board X\/Y is available for pieces placed on a board/);
}

// Relative parse: Mixed label / invalid / signed / bare positive.
assert.equal(PositionGeometry.parseRelativeOffset("Mixed"), null);
assert.equal(PositionGeometry.parseRelativeOffset("abc"), null);
assert.equal(PositionGeometry.parseRelativeOffset(""), null);
assert.equal(PositionGeometry.parseRelativeOffset("+5"), 5);
assert.equal(PositionGeometry.parseRelativeOffset("-2.5"), -2.5);
assert.equal(PositionGeometry.parseRelativeOffset("5"), 5);
assert.equal(PositionGeometry.parseRelativeOffset("0"), 0);

// Group X+ twice keeps relative gaps and Mixed display.
{
    const fresh = SessionDocument.buildFromProjection(projection, layout);
    const hist = History.create(fresh);
    const local = createStore({ projection, order_name: "O", plan_name: "P" });
    local.attachSession(hist.get(), hist);
    const beforeA = PositionGeometry.boardPositionForPiece(local.snapshot().session, keyA);
    const beforeB = PositionGeometry.boardPositionForPiece(local.snapshot().session, keyB);
    const gapX = beforeB.x - beforeA.x;
    const gapY = beforeB.y - beforeA.y;
    const undoBefore = local.snapshot().canUndo;
    assert.equal(applyGroupStep(local, [keyA, keyB], "x", 1).ok, true);
    assert.equal(applyGroupStep(local, [keyA, keyB], "x", 1).ok, true);
    const afterA = PositionGeometry.boardPositionForPiece(local.snapshot().session, keyA);
    const afterB = PositionGeometry.boardPositionForPiece(local.snapshot().session, keyB);
    assert.equal(PositionGeometry.formatMm(afterA.x), PositionGeometry.formatMm(beforeA.x + 2));
    assert.equal(PositionGeometry.formatMm(afterB.x), PositionGeometry.formatMm(beforeB.x + 2));
    assert.equal(PositionGeometry.formatMm(afterA.y), PositionGeometry.formatMm(beforeA.y));
    assert.equal(PositionGeometry.formatMm(afterB.y), PositionGeometry.formatMm(beforeB.y));
    assert.equal(afterB.x - afterA.x, gapX);
    assert.equal(afterB.y - afterA.y, gapY);
    const mixed = PositionGeometry.selectionPositionModel(local.snapshot().session, [keyA, keyB]);
    assert.equal(mixed.displayX, "Mixed");
    assert.equal(mixed.displayY, "Mixed");
    assert.equal(local.snapshot().canUndo, true);
    assert.notEqual(local.snapshot().canUndo, undoBefore);
}

// Relative typed offsets + zero does not create history.
{
    const fresh = SessionDocument.buildFromProjection(projection, layout);
    const hist = History.create(fresh);
    const local = createStore({ projection, order_name: "O", plan_name: "P" });
    local.attachSession(hist.get(), hist);
    const beforeA = PositionGeometry.boardPositionForPiece(local.snapshot().session, keyA);
    const beforeB = PositionGeometry.boardPositionForPiece(local.snapshot().session, keyB);
    assert.equal(applyGroupRelative(local, [keyA, keyB], "x", "+5").ok, true);
    assert.equal(
        PositionGeometry.formatMm(PositionGeometry.boardPositionForPiece(local.snapshot().session, keyA).x),
        PositionGeometry.formatMm(beforeA.x + 5)
    );
    assert.equal(
        PositionGeometry.formatMm(PositionGeometry.boardPositionForPiece(local.snapshot().session, keyB).x),
        PositionGeometry.formatMm(beforeB.x + 5)
    );
    // Y -2.5 lowers displayed Y (moves group down internally).
    assert.equal(applyGroupRelative(local, [keyA, keyB], "y", "-2.5").ok, true);
    assert.equal(
        PositionGeometry.formatMm(PositionGeometry.boardPositionForPiece(local.snapshot().session, keyA).y),
        PositionGeometry.formatMm(beforeA.y - 2.5)
    );
    const fpA = MoveGeometry.footprint(local.snapshot().session.pieces[keyA]).bounds;
    const fpA0 = MoveGeometry.footprint(fresh.pieces[keyA]).bounds;
    assert.equal(PositionGeometry.formatMm(fpA.y), PositionGeometry.formatMm(fpA0.y + 2.5));
    const undoBefore = local.snapshot().canUndo;
    const zero = applyGroupRelative(local, [keyA, keyB], "x", "0");
    assert.equal(zero.ok, true);
    assert.equal(zero.unchanged, true);
    assert.equal(local.snapshot().canUndo, undoBefore);
    assert.equal(applyGroupRelative(local, [keyA, keyB], "x", "NaN").ok, false);
}

// Keyboard group nudge net +1 X.
{
    const fresh = SessionDocument.buildFromProjection(projection, layout);
    const hist = History.create(fresh);
    const local = createStore({ projection, order_name: "O", plan_name: "P" });
    local.attachSession(hist.get(), hist);
    const startA = PositionGeometry.boardPositionForPiece(local.snapshot().session, keyA);
    const startB = PositionGeometry.boardPositionForPiece(local.snapshot().session, keyB);
    assert.equal(applyGroupNudge(local, [keyA, keyB], "ArrowRight").ok, true);
    assert.equal(applyGroupNudge(local, [keyA, keyB], "ArrowRight").ok, true);
    assert.equal(applyGroupNudge(local, [keyA, keyB], "ArrowDown").ok, true);
    assert.equal(applyGroupNudge(local, [keyA, keyB], "ArrowUp").ok, true);
    assert.equal(applyGroupNudge(local, [keyA, keyB], "ArrowLeft").ok, true);
    const endA = PositionGeometry.boardPositionForPiece(local.snapshot().session, keyA);
    const endB = PositionGeometry.boardPositionForPiece(local.snapshot().session, keyB);
    assert.equal(PositionGeometry.formatMm(endA.x), PositionGeometry.formatMm(startA.x + 1));
    assert.equal(PositionGeometry.formatMm(endB.x), PositionGeometry.formatMm(startB.x + 1));
    assert.equal(PositionGeometry.formatMm(endA.y), PositionGeometry.formatMm(startA.y));
    assert.equal(PositionGeometry.formatMm(endB.y), PositionGeometry.formatMm(startB.y));
}

// Atomic undo/redo for one group commit.
{
    const fresh = SessionDocument.buildFromProjection(projection, layout);
    const hist = History.create(fresh);
    const local = createStore({ projection, order_name: "O", plan_name: "P" });
    local.attachSession(hist.get(), hist);
    const startA = PositionGeometry.boardPositionForPiece(local.snapshot().session, keyA);
    const startB = PositionGeometry.boardPositionForPiece(local.snapshot().session, keyB);
    const result = applyGroupRelative(local, [keyA, keyB], "x", 5);
    assert.equal(result.ok, true);
    assert.equal(
        PositionGeometry.formatMm(PositionGeometry.boardPositionForPiece(local.snapshot().session, keyA).x),
        PositionGeometry.formatMm(startA.x + 5)
    );
    assert.equal(
        PositionGeometry.formatMm(PositionGeometry.boardPositionForPiece(local.snapshot().session, keyB).x),
        PositionGeometry.formatMm(startB.x + 5)
    );
    local.undo();
    assert.equal(
        PositionGeometry.formatMm(PositionGeometry.boardPositionForPiece(local.snapshot().session, keyA).x),
        PositionGeometry.formatMm(startA.x)
    );
    assert.equal(
        PositionGeometry.formatMm(PositionGeometry.boardPositionForPiece(local.snapshot().session, keyB).x),
        PositionGeometry.formatMm(startB.x)
    );
    local.redo();
    assert.equal(
        PositionGeometry.formatMm(PositionGeometry.boardPositionForPiece(local.snapshot().session, keyA).x),
        PositionGeometry.formatMm(startA.x + 5)
    );
    assert.equal(
        PositionGeometry.formatMm(PositionGeometry.boardPositionForPiece(local.snapshot().session, keyB).x),
        PositionGeometry.formatMm(startB.x + 5)
    );
}

// Reject board exit for any member — no partial move / no history.
{
    const fresh = SessionDocument.buildFromProjection(projection, layout);
    const hist = History.create(fresh);
    const local = createStore({ projection, order_name: "O", plan_name: "P" });
    local.attachSession(hist.get(), hist);
    const before = JSON.stringify(local.snapshot().session.pieces);
    const undoBefore = local.snapshot().canUndo;
    const rejected = applyGroupRelative(local, [keyA, keyB], "x", 900);
    assert.equal(rejected.ok, false);
    assert.equal(JSON.stringify(local.snapshot().session.pieces), before);
    assert.equal(local.snapshot().canUndo, undoBefore);
}

// Reject group overlap / kerf against a non-selected neighbour.
{
    const fresh = SessionDocument.buildFromProjection(projection, layout);
    const hist = History.create(fresh);
    const local = createStore({ projection, order_name: "O", plan_name: "P" });
    local.attachSession(hist.get(), hist);
    // Park A below and under B in X. Y+125 moves up into B (Poly tagged along).
    assert.equal(applyAxis(local, keyA, "x", 300).ok, true, "park A x");
    assert.equal(applyAxis(local, keyA, "y", 360).ok, true, "park A y");
    const before = JSON.stringify(local.snapshot().session.pieces);
    const undoBefore = local.snapshot().canUndo;
    const collide = applyGroupRelative(local, [keyA, keyPoly], "y", 125);
    assert.equal(collide.ok, false, collide.reason || "expected group kerf rejection");
    assert.equal(JSON.stringify(local.snapshot().session.pieces), before);
    assert.equal(local.snapshot().canUndo, undoBefore);
}

// Group Y+ step raises displayed Y and moves pieces up internally.
{
    const fresh = SessionDocument.buildFromProjection(projection, layout);
    const hist = History.create(fresh);
    const local = createStore({ projection, order_name: "O", plan_name: "P" });
    local.attachSession(hist.get(), hist);
    const beforeA = PositionGeometry.boardPositionForPiece(local.snapshot().session, keyA);
    const beforeB = PositionGeometry.boardPositionForPiece(local.snapshot().session, keyB);
    const fpBeforeA = MoveGeometry.footprint(local.snapshot().session.pieces[keyA]).bounds;
    assert.equal(applyGroupStep(local, [keyA, keyB], "y", 1).ok, true);
    const afterA = PositionGeometry.boardPositionForPiece(local.snapshot().session, keyA);
    const afterB = PositionGeometry.boardPositionForPiece(local.snapshot().session, keyB);
    const fpAfterA = MoveGeometry.footprint(local.snapshot().session.pieces[keyA]).bounds;
    assert.equal(PositionGeometry.formatMm(afterA.y), PositionGeometry.formatMm(beforeA.y + 1));
    assert.equal(PositionGeometry.formatMm(afterB.y), PositionGeometry.formatMm(beforeB.y + 1));
    assert.equal(PositionGeometry.formatMm(fpAfterA.y), PositionGeometry.formatMm(fpBeforeA.y - 1));
    assert.equal(afterB.y - afterA.y, beforeB.y - beforeA.y);
}

// Mixed board+outside selection is not editable / rejects move.
{
    const mixedScope = PositionGeometry.selectionPositionModel(session, [keyA, keyOut]);
    assert.ok(mixedScope);
    assert.equal(mixedScope.mixed, true);
    assert.equal(mixedScope.editable, false);
    const rejected = PositionGeometry.proposeGroupAxisStep(session, [keyA, keyOut], "x", 1);
    assert.equal(rejected.ok, false);
    assert.equal(rejected.code, PositionGeometry.CODE.MIXED_SCOPE);
}

// Outside-only pair can move without gaining a sheet.
{
    const proj2 = JSON.parse(JSON.stringify(projection));
    // Keep free-space pieces clear of board extents so +1 mm never clips a board edge.
    const outA = proj2.pieces.find((piece) => piece.piece_instance_id === "pi-out");
    outA.placement_cm = { x: 200, y: 0, w: 5, h: 5 };
    const outEl = proj2.elements.find((element) => element.piece_instance_id === "pi-out");
    outEl.geometry = { outer: [[2000, 0], [2050, 0], [2050, 50], [2000, 50]] };
    outEl.payload = { placement_cm: outA.placement_cm };
    proj2.pieces.push({
        piece_id: 5,
        piece_instance_id: "pi-out-2",
        label: "OUT2",
        sheet_no: null,
        placement_cm: { x: 220, y: 0, w: 5, h: 5 },
    });
    proj2.elements.push({
        element_id: "e-out-2",
        kind: "finished_outline",
        piece_id: 5,
        piece_instance_id: "pi-out-2",
        sheet_no: null,
        geometry: { outer: [[2200, 0], [2250, 0], [2250, 50], [2200, 50]] },
        payload: { placement_cm: { x: 220, y: 0, w: 5, h: 5 } },
    });
    const layout2 = CanvasRenderer.sheetLayout(proj2.sheets, 1);
    const fresh = SessionDocument.buildFromProjection(proj2, layout2);
    const hist = History.create(fresh);
    const local = createStore({ projection: proj2, order_name: "O", plan_name: "P" });
    local.attachSession(hist.get(), hist);
    const keyOut2 = "instance:pi-out-2";
    const model = PositionGeometry.selectionPositionModel(local.snapshot().session, [keyOut, keyOut2]);
    assert.equal(model.editable, true);
    const moved = applyGroupStep(local, [keyOut, keyOut2], "x", 1);
    assert.equal(moved.ok, true, moved.reason || "outside group move");
    assert.equal(local.snapshot().session.pieces[keyOut].sheet_no, null);
    assert.equal(local.snapshot().session.pieces[keyOut2].sheet_no, null);
}

// Cross-sheet selection rejected.
{
    const proj2 = JSON.parse(JSON.stringify(projection));
    proj2.sheets.push({
        sheet_no: 2,
        full_width_cm: 100,
        full_length_cm: 100,
        applied_trim_width_cm: 1,
        applied_trim_length_cm: 1,
    });
    proj2.pieces.push({
        piece_id: 6,
        piece_instance_id: "pi-c",
        label: "C",
        sheet_no: 2,
        placement_cm: { x: 5, y: 5, w: 10, h: 10 },
    });
    proj2.elements.push({
        element_id: "e6",
        kind: "finished_outline",
        piece_id: 6,
        piece_instance_id: "pi-c",
        sheet_no: 2,
        geometry: { outer: [[50, 50], [150, 50], [150, 150], [50, 150]] },
        payload: { placement_cm: { x: 5, y: 5, w: 10, h: 10 } },
    });
    const layout2 = CanvasRenderer.sheetLayout(proj2.sheets, 1);
    const fresh = SessionDocument.buildFromProjection(proj2, layout2);
    const keyC = "instance:pi-c";
    const model = PositionGeometry.selectionPositionModel(fresh, [keyA, keyC]);
    assert.equal(model.editable, false);
    const rejected = PositionGeometry.proposeGroupAxisStep(fresh, [keyA, keyC], "x", 1);
    assert.equal(rejected.ok, false);
    assert.equal(rejected.code, PositionGeometry.CODE.CROSS_SHEET);
}

console.log("board_editor_position_bar.test.js: ok");
