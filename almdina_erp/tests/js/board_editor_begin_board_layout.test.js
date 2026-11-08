"use strict";

/**
 * Begin-from-current-source must place boards on the 2×N workspace grid.
 * Collapsed saved origins (all boards at one point) must not stack on reopen.
 */

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
        "public/js/board_editor/rotation_geometry.js",
        "public/js/board_editor/canvas_renderer.js",
        "public/js/board_editor/store.js",
    ];
    const context = {
        __: (message) => message,
        frappe: { utils: { escape_html: (value) => String(value) } },
    };
    context.window = context;
    context.globalThis = context;
    vm.createContext(context);
    files.forEach((relative) => {
        vm.runInContext(fs.readFileSync(path.join(root, relative), "utf8"), context, {
            filename: relative,
        });
    });
    return context.window.AlmdinaBoardEditor;
}

const editor = load();
const { SessionDocument, MoveGeometry, CanvasRenderer, createStore, History } = editor;

function sheetsTwo() {
    return [
        { sheet_no: 1, full_width_cm: 122, full_length_cm: 244 },
        { sheet_no: 2, full_width_cm: 80, full_length_cm: 160 },
    ];
}

function sheetsThree() {
    return [
        ...sheetsTwo(),
        { sheet_no: 3, full_width_cm: 100, full_length_cm: 200 },
    ];
}

function projectionFromSheets(sheets) {
    return {
        board: { kerf_cm: 0.4 },
        sheets,
        pieces: [
            {
                piece_id: 1,
                piece_instance_id: "pi-a",
                label: "A",
                sheet_no: 1,
                placement_cm: { x: 1.5, y: 2.5, w: 20, h: 10 },
                allow_rotation: true,
                allow_rotation_proven: true,
            },
            {
                piece_id: 2,
                piece_instance_id: "pi-b",
                label: "B",
                sheet_no: 2,
                placement_cm: { x: 3, y: 4, w: 8, h: 8 },
                glass_host_piece_id: 1,
            },
            {
                piece_id: 3,
                piece_instance_id: "pi-c",
                label: "C",
                sheet_no: sheets.length >= 3 ? 3 : 1,
                placement_cm: { x: 0.5, y: 0.5, w: 12, h: 12 },
            },
        ],
        elements: [],
        layers: [],
    };
}

function piece(session, instance) {
    return Object.values(session.pieces).find((row) => row.piece_instance_id === instance);
}

function boardBounds(board) {
    const title = Number(board.title_band_mm) || SessionDocument.TITLE_BAND_MM;
    return {
        x0: Number(board.origin_x_mm) || 0,
        y0: (Number(board.origin_y_mm) || 0) - title,
        x1: (Number(board.origin_x_mm) || 0) + (Number(board.width_mm) || 0),
        y1: (Number(board.origin_y_mm) || 0) + (Number(board.height_mm) || 0),
    };
}

function assertNoBoardOverlap(session) {
    const boards = Object.values(session.boards || {});
    for (let i = 0; i < boards.length; i += 1) {
        for (let j = i + 1; j < boards.length; j += 1) {
            const a = boardBounds(boards[i]);
            const b = boardBounds(boards[j]);
            const overlap = !(a.x1 <= b.x0 || b.x1 <= a.x0 || a.y1 <= b.y0 || b.y1 <= a.y0);
            assert.equal(
                overlap,
                false,
                `boards ${boards[i].sheet_no} and ${boards[j].sheet_no} overlap`
            );
        }
    }
}

function collapsedIdentityLayout(session) {
    const exported = SessionDocument.exportLayout(session);
    exported.boards = exported.boards.map((board) => ({
        ...board,
        origin_x_mm: 0,
        origin_y_mm: SessionDocument.TITLE_BAND_MM,
        user_moved: false,
    }));
    return exported;
}

function runCase(sheetList) {
    const projection = projectionFromSheets(sheetList);
    const grid = CanvasRenderer.sheetLayout(projection.sheets, 2);
    const base = SessionDocument.buildFromProjection(projection, grid);
    assertNoBoardOverlap(base);

    // Defective begin payload: every board at the same origin.
    const stacked = collapsedIdentityLayout(base);
    assert.equal(SessionDocument.boardsShareCollapsedDefaultOrigin(stacked.boards), true);
    const healed = SessionDocument.applySavedLayout(base, stacked);
    assert.equal(healed.ok, true);
    assertNoBoardOverlap(healed.session);
    assert.equal(piece(healed.session, "pi-a").local_x_mm, 15);
    assert.equal(piece(healed.session, "pi-a").local_y_mm, 25);
    assert.equal(piece(healed.session, "pi-a").rotation_deg, 0);
    assert.equal(piece(healed.session, "pi-b").glass_host_piece_id, 1);
    assert.equal(piece(healed.session, "pi-b").sheet_no, 2);

    // Correct begin/grid origins persist through save → reopen.
    const spaced = SessionDocument.exportLayout(healed.session);
    assert.equal(SessionDocument.boardsShareCollapsedDefaultOrigin(spaced.boards), false);
    const reopened = SessionDocument.applySavedLayout(
        SessionDocument.buildFromProjection(projection, grid),
        spaced
    );
    assert.equal(reopened.ok, true);
    assert.equal(
        reopened.session.boards["1"].origin_x_mm,
        healed.session.boards["1"].origin_x_mm
    );
    assert.equal(
        reopened.session.boards["2"].origin_x_mm,
        healed.session.boards["2"].origin_x_mm
    );
    if (sheetList.length >= 3) {
        assert.equal(
            reopened.session.boards["3"].origin_y_mm,
            healed.session.boards["3"].origin_y_mm
        );
    }
    assertNoBoardOverlap(reopened.session);

    // User-moved board survives selection/repaint-style relayout.
    let moved = MoveGeometry.applyBoardMove(healed.session, {
        sheet_no: 1,
        origin_x_mm: 40,
        origin_y_mm: 80,
    });
    assert.equal(moved.boards["1"].user_moved, true);
    assert.equal(moved.boards["1"].origin_x_mm, 40);
    const afterRelayout = SessionDocument.relayoutUnmovedBoards(
        moved,
        CanvasRenderer.sheetLayout(projection.sheets, 2)
    );
    assert.equal(afterRelayout.boards["1"].origin_x_mm, 40);
    assert.equal(afterRelayout.boards["1"].user_moved, true);
    // Sheet 2 was unmoved — may refresh to grid; sheet 1 stays.
    assert.equal(afterRelayout.boards["2"].user_moved, false);

    // Tree-style sheet select + move piece between boards keep locals/hosting.
    const store = createStore({ projection, editor_draft: { compatible: true } });
    const history = History.create(afterRelayout);
    store.attachSession(history.get(), history);
    store.selectSheet(2);
    assert.equal(store.snapshot().selectedSheetNo, 2);
    assert.equal(store.snapshot().expandedSheets["2"], true);
    const transferred = MoveGeometry.applyPieceMove(afterRelayout, {
        piece_key: piece(afterRelayout, "pi-a").piece_key,
        local_x_mm: 12,
        local_y_mm: 18,
        sheet_no: 2,
        delta_x_mm: 0,
        delta_y_mm: 0,
    });
    assert.equal(piece(transferred, "pi-a").sheet_no, 2);
    assert.equal(piece(transferred, "pi-a").local_x_mm, 12);
    assert.equal(piece(transferred, "pi-b").glass_host_piece_id, 1);
}

runCase(sheetsTwo());
runCase(sheetsThree());

// Spaced saved layout must not be treated as collapsed.
{
    const projection = projectionFromSheets(sheetsTwo());
    const grid = CanvasRenderer.sheetLayout(projection.sheets, 2);
    const base = SessionDocument.buildFromProjection(projection, grid);
    const spaced = SessionDocument.exportLayout(base);
    spaced.boards[0].origin_x_mm = 0;
    spaced.boards[0].origin_y_mm = 36;
    spaced.boards[1].origin_x_mm = 1300;
    spaced.boards[1].origin_y_mm = 36;
    assert.equal(SessionDocument.boardsShareCollapsedDefaultOrigin(spaced.boards), false);
    const applied = SessionDocument.applySavedLayout(base, spaced);
    assert.equal(applied.session.boards["2"].origin_x_mm, 1300);
}

console.log("board_editor_begin_board_layout.test.js: ok");
