"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.resolve(__dirname, "../..");

function load() {
    const files = [
        "public/js/board_editor/history.js",
        "public/js/board_editor/session_document.js",
        "public/js/board_editor/move_geometry.js",
        "public/js/board_editor/snap_geometry.js",
        "public/js/board_editor/rotation_geometry.js",
        "public/js/board_editor/distribution.js",
        "public/js/door_cutting_order/cutting_plan/door_cutting_order_edge_display.js",
        "public/js/board_editor/plan_display_style.js",
        "public/js/board_editor/plan_edge_marks.js",
        "public/js/board_editor/store.js",
        "public/js/board_editor/canvas_renderer.js",
        "public/js/board_editor/sidebar_renderer.js",
    ];
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

const editor = load();
const {
    History,
    SessionDocument,
    MoveGeometry,
    SnapGeometry,
    RotationGeometry,
    Distribution,
    CanvasRenderer,
    SidebarRenderer,
} = editor;

const projection = {
    board: { kerf_cm: 0.4, width_cm: 122, length_cm: 244 },
    edge_display: { default_edge_type: "" },
    sheets: [
        {
            sheet_no: 1,
            resource_kind: "FULL_BOARD",
            full_width_cm: 122,
            full_length_cm: 244,
            applied_trim_width_cm: 0,
            applied_trim_length_cm: 0,
            usable_width_cm: 122,
            usable_length_cm: 244,
        },
        {
            sheet_no: 2,
            resource_kind: "OFFCUT",
            full_width_cm: 40,
            full_length_cm: 40,
            applied_trim_width_cm: 0,
            applied_trim_length_cm: 0,
            usable_width_cm: 40,
            usable_length_cm: 40,
        },
    ],
    pieces: [
        {
            piece_id: 1,
            piece_instance_id: "pi-host",
            label: "HOST",
            sheet_no: 1,
            placement_cm: { x: 10, y: 10, w: 40, h: 30 },
            glass_hole_local_mm: [[150, 150], [250, 150], [250, 250], [150, 250]],
        },
        {
            piece_id: 2,
            piece_instance_id: "pi-guest",
            label: "GUEST",
            sheet_no: 1,
            placement_cm: { x: 16, y: 16, w: 8, h: 8 },
            glass_host_piece_id: 1,
        },
        {
            piece_id: 3,
            piece_instance_id: "pi-out",
            label: "OUTSIDE",
            sheet_no: null,
            placement_cm: { x: 200, y: 20, w: 20, h: 20 },
        },
        {
            piece_id: 4,
            piece_instance_id: "pi-off",
            label: "OFFCUT-PIECE",
            sheet_no: 2,
            placement_cm: { x: 2, y: 2, w: 10, h: 10 },
        },
    ],
    elements: [
        {
            element_id: "sheet-1",
            kind: "sheet_outline",
            sheet_no: 1,
            layer_match_key: "SHEET",
            payload: {
                resource_kind: "FULL_BOARD",
                full_width_cm: 122,
                full_length_cm: 244,
                usable_width_cm: 122,
                usable_length_cm: 244,
                applied_trim_width_cm: 0,
                applied_trim_length_cm: 0,
            },
        },
        {
            element_id: "sheet-2",
            kind: "sheet_outline",
            sheet_no: 2,
            layer_match_key: "SHEET",
            payload: {
                resource_kind: "OFFCUT",
                full_width_cm: 40,
                full_length_cm: 40,
                usable_width_cm: 40,
                usable_length_cm: 40,
                applied_trim_width_cm: 0,
                applied_trim_length_cm: 0,
            },
        },
        {
            element_id: "host-outline",
            kind: "finished_outline",
            piece_id: 1,
            piece_instance_id: "pi-host",
            sheet_no: 1,
            layer_match_key: "GEOMETRY",
            geometry: { outer: [[100, 100], [500, 100], [500, 400], [100, 400]] },
        },
        {
            element_id: "guest-outline",
            kind: "finished_outline",
            piece_id: 2,
            piece_instance_id: "pi-guest",
            sheet_no: 1,
            layer_match_key: "GEOMETRY",
            geometry: { outer: [[160, 160], [240, 160], [240, 240], [160, 240]] },
        },
        {
            element_id: "out-outline",
            kind: "finished_outline",
            piece_id: 3,
            piece_instance_id: "pi-out",
            sheet_no: null,
            layer_match_key: "GEOMETRY",
            geometry: { outer: [[2000, 200], [2200, 200], [2200, 400], [2000, 400]] },
        },
        {
            element_id: "off-outline",
            kind: "finished_outline",
            piece_id: 4,
            piece_instance_id: "pi-off",
            sheet_no: 2,
            layer_match_key: "GEOMETRY",
            geometry: { outer: [[20, 20], [120, 20], [120, 120], [20, 120]] },
        },
        {
            element_id: "cut-1",
            kind: "cut_path",
            sheet_no: 1,
            layer_match_key: "CUT",
            geometry: { path: [[0, 0], [10, 0]], closed: false },
        },
        {
            element_id: "free-text",
            kind: "text_label",
            sheet_no: 1,
            layer_match_key: "TEXT",
            payload: { text: "UNBOUND", x_mm: 10, y_mm: 10, height_mm: 8 },
        },
    ],
    layers: [],
    unplaced: [],
};

const layout = {
    positions: {
        1: { originX: 0, originY: 36, widthMm: 1220, heightMm: 2440, trimX: 0, trimY: 0 },
        2: { originX: 1400, originY: 36, widthMm: 400, heightMm: 400, trimX: 0, trimY: 0 },
    },
};

function freshSession() {
    return SessionDocument.buildFromProjection(projection, layout);
}

const sourceBefore = JSON.stringify(projection);
const session = freshSession();
assert.equal(JSON.stringify(projection), sourceBefore);
assert.equal(session.pieces["instance:pi-host"].piece_key, "instance:pi-host");
assert.equal(session.pieces["instance:pi-guest"].glass_host_key, "instance:pi-host");

const hostKey = "instance:pi-host";
const guestKey = "instance:pi-guest";
const outKey = "instance:pi-out";
const offKey = "instance:pi-off";

session.pieces[hostKey].rotation_deg = 37;
const onBoard = Distribution.excludePiece(session, hostKey);
assert.equal(onBoard.ok, true);
assert.equal(JSON.stringify(onBoard.piece_keys), JSON.stringify([hostKey, guestKey]));
assert.equal(onBoard.session.pieces[hostKey].distribution, "excluded");
assert.equal(onBoard.session.pieces[guestKey].distribution, "excluded");
assert.equal(onBoard.session.pieces[guestKey].glass_host_key, hostKey);
assert.equal(onBoard.session.pieces[guestKey].exclusion_reason, Distribution.REASON_WITH_HOST);
assert.equal(onBoard.session.pieces[hostKey].rotation_deg, 37);
assert.equal(onBoard.session.pieces[hostKey].piece_instance_id, "pi-host");
assert.ok(onBoard.session.stale_cut_path_sheets.includes("1"));
assert.ok(onBoard.session.stale_unbound_text_sheets.includes("1"));
assert.equal(SessionDocument.hostingRoots(onBoard.session, 1).length, 0);
assert.equal(SessionDocument.piecesBySheet(onBoard.session).outside.some((piece) => piece.piece_key === hostKey), false);
assert.equal(SessionDocument.excludedRoots(onBoard.session)[0].piece_key, hostKey);

const guestOnly = Distribution.excludePiece(freshSession(), guestKey);
assert.equal(guestOnly.ok, true);
assert.equal(JSON.stringify(guestOnly.piece_keys), JSON.stringify([guestKey]));
assert.equal(guestOnly.session.pieces[guestKey].glass_host_key, null);
assert.equal(guestOnly.session.pieces[guestKey].glass_host_piece_id, null);
assert.notEqual(guestOnly.session.pieces[hostKey].distribution, "excluded");

const outside = Distribution.excludePiece(freshSession(), outKey);
assert.equal(outside.ok, true);
assert.equal(outside.session.pieces[outKey].sheet_no, null);
assert.equal(SessionDocument.hostingRoots(outside.session, null).some((node) => node.piece_key === outKey), false);

const blocked = Distribution.excludePiece(onBoard.session, hostKey);
assert.equal(blocked.ok, false);
assert.equal(blocked.code, "noop");

const history = History.create(session);
const committed = history.commit(onBoard.session);
assert.equal(committed.pieces[hostKey].distribution, "excluded");
assert.equal(history.state().canUndo, true);
const undo = history.undo();
assert.equal(undo.pieces[hostKey].rotation_deg, 37);
assert.notEqual(undo.pieces[hostKey].distribution, "excluded");
assert.equal(undo.pieces[guestKey].glass_host_key, hostKey);
const redo = history.redo();
assert.equal(redo.pieces[hostKey].distribution, "excluded");
assert.equal(redo.pieces[hostKey].rotation_deg, 37);
history.commit(history.get());
const skippedEmpty = history.undo();
assert.notEqual(skippedEmpty.pieces[hostKey].distribution, "excluded");
history.redo();

const returned = Distribution.returnPieceToStaging(redo, hostKey);
assert.equal(returned.ok, true);
assert.equal(returned.session.pieces[hostKey].distribution, "active");
assert.equal(returned.session.pieces[hostKey].sheet_no, null);
assert.equal(returned.session.pieces[hostKey].rotation_deg, 37);
assert.equal(returned.session.pieces[guestKey].distribution, "excluded");
assert.equal(Distribution.returnPieceToStaging(returned.session, hostKey).ok, false);
history.commit(returned.session);
assert.equal(history.undo().pieces[hostKey].distribution, "excluded");
assert.equal(history.redo().pieces[hostKey].sheet_no, null);

const rotated = freshSession();
rotated.pieces[outKey].rotation_deg = 12.5;
const historyOutside = History.create(rotated);
historyOutside.commit(Distribution.excludePiece(rotated, outKey).session);
assert.equal(historyOutside.undo().pieces[outKey].rotation_deg, 12.5);
assert.equal(historyOutside.redo().pieces[outKey].distribution, "excluded");

const crowded = freshSession();
const hostWorld = MoveGeometry.worldFootprint(crowded.pieces[hostKey], crowded.boards);
const blockedDrop = MoveGeometry.validatePieceDrop(crowded, outKey, hostWorld.bounds.x, hostWorld.bounds.y);
const withoutHost = Distribution.excludePiece(crowded, hostKey).session;
const clearDrop = MoveGeometry.validatePieceDrop(withoutHost, outKey, hostWorld.bounds.x, hostWorld.bounds.y);
assert.equal(blockedDrop.ok, false);
assert.equal(clearDrop.ok, true);

const magnet = freshSession();
const hostFoot = MoveGeometry.worldFootprint(magnet.pieces[hostKey], magnet.boards);
const mover = magnet.pieces[outKey];
const origin = MoveGeometry.sheetOriginMm(magnet.boards, 1);
mover.sheet_no = 1;
mover.local_x_mm = hostFoot.bounds.x + hostFoot.bounds.w + 10 - origin.x;
mover.local_y_mm = hostFoot.bounds.y - origin.y;
mover.outline_mm = [
    [mover.local_x_mm, mover.local_y_mm],
    [mover.local_x_mm + 200, mover.local_y_mm],
    [mover.local_x_mm + 200, mover.local_y_mm + 200],
    [mover.local_x_mm, mover.local_y_mm + 200],
];
mover.pivot_mm = { x: mover.local_x_mm + 100, y: mover.local_y_mm + 100 };
mover.entry_pivot_mm = { x: mover.pivot_mm.x, y: mover.pivot_mm.y };
const moverWorld = MoveGeometry.worldFootprint(mover, magnet.boards);
const snapTowardHost = SnapGeometry.suggestPieceSnap(
    magnet,
    outKey,
    moverWorld.bounds.x - 6,
    moverWorld.bounds.y,
    { scale: 1, thresholdMm: 40 }
);
const magnetWithoutHost = Distribution.excludePiece(magnet, hostKey).session;
const snapWithoutHost = SnapGeometry.suggestPieceSnap(
    magnetWithoutHost,
    outKey,
    moverWorld.bounds.x - 6,
    moverWorld.bounds.y,
    { scale: 1, thresholdMm: 40 }
);
assert.equal(String(snapTowardHost.source || "").includes(hostKey), true);
assert.equal(String(snapWithoutHost.source || "").includes(hostKey), false);
assert.equal(String(snapWithoutHost.source || "").includes(guestKey), false);

const boardSession = freshSession();
boardSession.pieces[hostKey].rotation_deg = 37;
const beforeWorld = MoveGeometry.worldFootprint(boardSession.pieces[hostKey], boardSession.boards);
const removed = Distribution.removeBoard(boardSession, 1);
assert.equal(removed.ok, true);
assert.equal(removed.session.boards["1"], undefined);
assert.equal(removed.session.boards["2"].sheet_no, 2);
assert.equal(removed.session.pieces[hostKey].sheet_no, null);
assert.equal(removed.session.pieces[guestKey].sheet_no, null);
assert.equal(removed.session.pieces[guestKey].glass_host_key, hostKey);
assert.equal(removed.session.pieces[hostKey].rotation_deg, 37);
assert.equal(removed.session.pieces[hostKey].piece_key, hostKey);
const afterWorld = MoveGeometry.worldFootprint(removed.session.pieces[hostKey], removed.session.boards);
assert.equal(afterWorld.bounds.x, beforeWorld.bounds.x);
assert.equal(afterWorld.bounds.y, beforeWorld.bounds.y);
assert.equal(Distribution.removeBoard(removed.session, 1).ok, false);
const excludedThenBoard = Distribution.excludePiece(freshSession(), hostKey);
const parkedWorld = MoveGeometry.worldFootprint(
    excludedThenBoard.session.pieces[hostKey],
    excludedThenBoard.session.boards
);
const boardAfterExclude = Distribution.removeBoard(excludedThenBoard.session, 1);
const parkedBack = Distribution.returnPieceToStaging(boardAfterExclude.session, hostKey);
const parkedAfter = MoveGeometry.worldFootprint(parkedBack.session.pieces[hostKey], parkedBack.session.boards);
assert.equal(parkedAfter.bounds.x, parkedWorld.bounds.x);
assert.equal(parkedAfter.bounds.y, parkedWorld.bounds.y);
assert.equal(parkedBack.session.pieces[hostKey].rotation_deg, 0);
const boardHistory = History.create(boardSession);
boardHistory.commit(removed.session);
const restoredBoard = boardHistory.undo();
assert.ok(restoredBoard.boards["1"]);
assert.equal(restoredBoard.pieces[hostKey].sheet_no, 1);
assert.equal(restoredBoard.pieces[guestKey].glass_host_key, hostKey);
assert.equal(boardHistory.redo().boards["1"], undefined);

const emptyBoards = Distribution.removeBoard(removed.session, 2);
assert.equal(emptyBoards.ok, true);
assert.equal(Object.keys(emptyBoards.session.boards).length, 0);
assert.equal(emptyBoards.session.pieces[offKey].sheet_no, null);
assert.equal(emptyBoards.session.pieces[hostKey].piece_instance_id, "pi-host");

const entry = History.create(freshSession());
entry.commit(onBoard.session);
entry.commit(removed.session);
const entryDoc = entry.restoreEntry();
assert.equal(entryDoc.pieces[hostKey].sheet_no, 1);
assert.notEqual(entryDoc.pieces[hostKey].distribution, "excluded");
assert.ok(entryDoc.boards["1"]);
assert.ok(entryDoc.boards["2"]);
assert.equal(entryDoc.pieces[guestKey].glass_host_key, hostKey);

assert.equal(Distribution.keyboardDeleteApplies({ tagName: "INPUT" }), false);
assert.equal(Distribution.keyboardDeleteApplies({ tagName: "TEXTAREA" }), false);
assert.equal(Distribution.keyboardDeleteApplies({ tagName: "DIV", isContentEditable: true }), false);
assert.equal(Distribution.keyboardDeleteApplies({ tagName: "BUTTON" }), true);
const controllerSource = fs.readFileSync(path.join(root, "public/js/board_editor/controller.js"), "utf8");
assert.match(controllerSource, /keyboardDeleteApplies\(event\.target\)/);
assert.match(controllerSource, /event\.key === "Delete"/);

assert.equal(JSON.stringify(projection), sourceBefore);
assert.equal(projection.pieces.length, 4);
assert.equal(projection.sheets[1].resource_kind, "OFFCUT");

function hostNode() {
    return {
        clientWidth: 1100,
        clientHeight: 760,
        style: {},
        __html: "",
        set innerHTML(value) { this.__html = String(value); },
        get innerHTML() { return this.__html; },
        querySelector() {
            return {
                scrollTop: 0,
                clientWidth: 1100,
                clientHeight: 700,
                scrollLeft: 0,
                scrollTop: 0,
                classList: { add() {}, remove() {} },
                style: {},
                addEventListener() {},
                querySelector() { return null; },
                querySelectorAll() { return []; },
                getBoundingClientRect() {
                    return { left: 0, top: 0, width: 1100, height: 700, right: 1100, bottom: 700 };
                },
            };
        },
        querySelectorAll() { return []; },
    };
}

function viewFor(document, selected) {
    return {
        projection,
        session: document,
        layerVisibility: {},
        expandedSheets: {},
        selectedPieceId: selected ? selected.piece_id : null,
        selectedPieceKey: selected ? selected.piece_key : null,
        selectedSheetNo: selected ? selected.sheet_no : null,
        selectedElementId: null,
        magnetEnabled: true,
        canUndo: false,
        canRedo: false,
        dropMessage: "",
        viewport: { scale: 0.25, opened: true, userAdjusted: true, cameraToken: 0 },
    };
}

const canvas = hostNode();
CanvasRenderer.render(canvas, viewFor(onBoard.session, null), {});
assert.equal(canvas.innerHTML.includes('data-piece-instance="pi-host"'), false);
assert.equal(canvas.innerHTML.includes('data-piece-instance="pi-guest"'), false);
assert.equal(canvas.innerHTML.includes("cut-1"), false);
assert.equal(canvas.innerHTML.includes("UNBOUND"), false);
assert.equal(canvas.innerHTML.includes('data-piece-instance="pi-off"'), true);
assert.equal(canvas.innerHTML.includes('data-board-drag="2"'), true);

const boardCanvas = hostNode();
CanvasRenderer.render(boardCanvas, viewFor(removed.session, null), {});
assert.equal(boardCanvas.innerHTML.includes('data-board-drag="1"'), false);
assert.equal(boardCanvas.innerHTML.includes('data-piece-instance="pi-host"'), true);
assert.equal(boardCanvas.innerHTML.includes('data-board-drag="2"'), true);
assert.equal(boardCanvas.innerHTML.includes(">Offcut<"), true);

const sidebar = hostNode();
SidebarRenderer.render(sidebar, viewFor(onBoard.session, onBoard.session.pieces[hostKey]), {});
assert.match(sidebar.innerHTML, /Excluded from distribution/);
assert.match(sidebar.innerHTML, /HOST/);
assert.match(sidebar.innerHTML, /Removed from the layout/);
assert.match(sidebar.innerHTML, /Removed with the host/);
assert.match(sidebar.innerHTML, /Return to staging/);
assert.equal(sidebar.innerHTML.includes(">OFFCUT<"), true);
assert.equal(sidebar.innerHTML.includes("Outside boards") && sidebar.innerHTML.includes("OUTSIDE"), true);

const selectedCanvas = hostNode();
CanvasRenderer.render(selectedCanvas, viewFor(freshSession(), freshSession().pieces[hostKey]), {});
assert.match(selectedCanvas.innerHTML, /Remove from distribution/);
assert.match(selectedCanvas.innerHTML, /Remove board from distribution/);
assert.equal(/class="alm-btn-secondary abe-remove-piece" disabled/.test(selectedCanvas.innerHTML), false);

console.log("board editor distribution ok");
