"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.resolve(__dirname, "../..");

function loadAll() {
    const files = [
        "public/js/board_editor/history.js",
        "public/js/board_editor/session_document.js",
        "public/js/board_editor/move_geometry.js",
        "public/js/board_editor/store.js",
    ];
    const context = {
        frappe: { utils: { escape_html: (value) => String(value) } },
        __: (message) => message,
    };
    context.window = context;
    context.globalThis = context;
    vm.createContext(context);
    files.forEach((relativePath) => {
        vm.runInContext(fs.readFileSync(path.join(root, relativePath), "utf8"), context);
    });
    return context.window.AlmdinaBoardEditor;
}

const editor = loadAll();
const { History, SessionDocument, MoveGeometry, createStore } = editor;

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
            piece_instance_id: "pi-host",
            label: "HOST",
            sheet_no: 1,
            placement_cm: { x: 10, y: 10, w: 40, h: 40 },
            // Piece-local manufacturing ring (placement 10×10 cm → usable 100,100).
            glass_hole_local_mm: [
                [50, 50],
                [150, 50],
                [150, 150],
                [50, 150],
            ],
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
            piece_instance_id: "pi-other",
            label: "OTHER",
            sheet_no: 1,
            placement_cm: { x: 70, y: 10, w: 20, h: 20 },
        },
        {
            piece_id: 4,
            label: "LEGACY",
            sheet_no: 2,
            placement_cm: { x: 5, y: 5, w: 10, h: 10 },
        },
        {
            piece_id: 5,
            piece_instance_id: "pi-special",
            label: "SPECIAL",
            sheet_no: 2,
            piece_type: "Special",
            placement_cm: { x: 20, y: 20, w: 10, h: 10 },
        },
        {
            piece_id: 6,
            piece_instance_id: "pi-cnc-raw",
            label: "CNC-RAW",
            sheet_no: 2,
            piece_type: "Special",
            geometry_source: "cnc_raw_rect",
            exact_geometry: false,
            special_representation: "cnc_raw",
            placement_cm: { x: 40, y: 40, w: 22, h: 21 },
            original_w: 22,
            original_h: 21,
        },
    ],
    elements: [
        {
            element_id: "e1",
            kind: "finished_outline",
            piece_id: 1,
            piece_instance_id: "pi-host",
            sheet_no: 1,
            layer_match_key: "GEOMETRY",
            geometry: {
                outer: [
                    [100, 100],
                    [500, 100],
                    [500, 500],
                    [100, 500],
                ],
            },
        },
        {
            element_id: "e2",
            kind: "finished_outline",
            piece_id: 2,
            piece_instance_id: "pi-guest",
            sheet_no: 1,
            layer_match_key: "GEOMETRY",
            geometry: {
                outer: [
                    [160, 160],
                    [240, 160],
                    [240, 240],
                    [160, 240],
                ],
            },
        },
        {
            element_id: "e3",
            kind: "placement_rect",
            piece_id: 3,
            piece_instance_id: "pi-other",
            sheet_no: 1,
            layer_match_key: "GEOMETRY",
            payload: { placement_cm: { x: 70, y: 10, w: 20, h: 20 } },
        },
        {
            element_id: "e5",
            kind: "unresolved",
            piece_id: 5,
            piece_instance_id: "pi-special",
            sheet_no: 2,
            layer_match_key: "SPECIAL",
            payload: {
                reason: "special_geometry_unavailable",
                placement_cm: { x: 20, y: 20, w: 10, h: 10 },
            },
        },
        {
            element_id: "e6",
            kind: "finished_outline",
            piece_id: 6,
            piece_instance_id: "pi-cnc-raw",
            sheet_no: 2,
            layer_match_key: "GEOMETRY",
            geometry: {
                outer: [
                    [400, 400],
                    [620, 400],
                    [620, 610],
                    [400, 610],
                ],
            },
            payload: {
                geometry_source: "cnc_raw_rect",
                special_representation: "cnc_raw",
                fill_role: "special",
            },
        },
        {
            element_id: "t1",
            kind: "text_label",
            piece_id: 1,
            piece_instance_id: "pi-host",
            sheet_no: 1,
            layer_match_key: "TEXT",
            payload: { text: "HOST", x_mm: 110, y_mm: 120, height_mm: 12 },
        },
        {
            element_id: "cut1",
            kind: "cut_path",
            sheet_no: 1,
            layer_match_key: "CUT_PATH",
            geometry: { path: [[0, 0], [100, 0]], closed: false },
        },
    ],
};

const layout = {
    positions: {
        1: { originX: 0, originY: 36, widthMm: 1000, heightMm: 1000, trimX: 0, trimY: 0 },
        2: { originX: 1048, originY: 36, widthMm: 1000, heightMm: 1000, trimX: 0, trimY: 0 },
    },
};

const session = SessionDocument.buildFromProjection(projection, layout);
assert.equal(session.pieces["instance:pi-host"].editable, true);
assert.equal(session.pieces["instance:pi-special"].editable, false);
assert.equal(session.pieces["instance:pi-special"].block_reason, "special_geometry_unavailable");
assert.equal(session.pieces["instance:pi-cnc-raw"].editable, true);
assert.equal(session.pieces["instance:pi-cnc-raw"].block_reason, null);
assert.equal(session.pieces["instance:pi-cnc-raw"].geometry_source, "cnc_raw_rect");
assert.equal(session.pieces["instance:pi-cnc-raw"].exact_geometry, false);
assert.equal(session.pieces["instance:pi-cnc-raw"].outline_mm.length, 4);
assert.equal(Object.prototype.hasOwnProperty.call(session.pieces, "instance:"), false);
assert.ok(!Object.values(session.pieces).some((piece) => piece.label === "LEGACY"));

const history = History.create(session);
const hostKey = "instance:pi-host";
const guestKey = "instance:pi-guest";
const otherKey = "instance:pi-other";

// CNC-raw stock rectangle can move on its board with kerf/collision rules.
{
    const rawKey = "instance:pi-cnc-raw";
    const moved = MoveGeometry.proposePieceDrop(history.get(), rawKey, 1048 + 450, 36 + 450);
    assert.equal(moved.ok, true, moved.code || "cnc raw move");
    assert.equal(moved.target_sheet_no, 2);
    const after = MoveGeometry.applyPieceMove(history.get(), {
        piece_key: rawKey,
        target_sheet_no: moved.target_sheet_no,
        local_x_mm: moved.local_x_mm,
        local_y_mm: moved.local_y_mm,
        delta_x_mm: moved.delta_x_mm,
        delta_y_mm: moved.delta_y_mm,
    });
    history.commit(after);
    assert.equal(history.get().pieces[rawKey].local_x_mm, moved.local_x_mm);
    history.undo();
    assert.equal(history.get().pieces[rawKey].local_x_mm, 400);
    history.redo();
    assert.equal(history.get().pieces[rawKey].local_x_mm, moved.local_x_mm);
    history.undo();
}

// Move host inside same board; guest follows once; identity stable.
const inside = MoveGeometry.proposePieceDrop(history.get(), hostKey, 120, 120);
assert.equal(inside.ok, true);
let next = MoveGeometry.applyPieceMove(history.get(), {
    piece_key: hostKey,
    target_sheet_no: inside.target_sheet_no,
    local_x_mm: inside.local_x_mm,
    local_y_mm: inside.local_y_mm,
    delta_x_mm: inside.delta_x_mm,
    delta_y_mm: inside.delta_y_mm,
});
history.commit(next);
assert.equal(history.get().pieces[hostKey].piece_instance_id, "pi-host");
assert.equal(history.get().pieces[guestKey].sheet_no, 1);
assert.ok(history.get().stale_cut_path_sheets.includes("1"));

history.undo();
assert.equal(history.get().pieces[hostKey].local_x_mm, 100);
history.redo();
assert.equal(history.get().pieces[hostKey].local_x_mm, inside.local_x_mm);

// Move to other board keeps piece_instance_id (clear of the special placeholder).
const toBoard2 = MoveGeometry.proposePieceDrop(
    history.get(),
    otherKey,
    1048 + 700,
    36 + 700
);
assert.equal(toBoard2.ok, true);
assert.equal(toBoard2.target_sheet_no, 2);
next = MoveGeometry.applyPieceMove(history.get(), {
    piece_key: otherKey,
    target_sheet_no: toBoard2.target_sheet_no,
    local_x_mm: toBoard2.local_x_mm,
    local_y_mm: toBoard2.local_y_mm,
    delta_x_mm: toBoard2.delta_x_mm,
    delta_y_mm: toBoard2.delta_y_mm,
});
history.commit(next);
assert.equal(history.get().pieces[otherKey].piece_instance_id, "pi-other");
assert.equal(history.get().pieces[otherKey].sheet_no, 2);

// Move outside then back.
const outside = MoveGeometry.proposePieceDrop(history.get(), otherKey, 2500, 50);
assert.equal(outside.ok, true);
assert.equal(outside.target_sheet_no, null);
next = MoveGeometry.applyPieceMove(history.get(), {
    piece_key: otherKey,
    target_sheet_no: null,
    local_x_mm: outside.local_x_mm,
    local_y_mm: outside.local_y_mm,
    delta_x_mm: outside.delta_x_mm,
    delta_y_mm: outside.delta_y_mm,
});
history.commit(next);
assert.equal(history.get().pieces[otherKey].sheet_no, null);
const back = MoveGeometry.proposePieceDrop(history.get(), otherKey, 1048 + 700, 36 + 700);
assert.equal(back.ok, true);
assert.equal(back.target_sheet_no, 2);

// Partial board overlap rejected and not committed.
const beforeReject = history.get();
const partial = MoveGeometry.proposePieceDrop(history.get(), otherKey, 980, 36 + 40);
assert.equal(partial.ok, false);
assert.match(partial.reason, /board edge|crosses/i);
assert.deepEqual(history.get().pieces[otherKey], beforeReject.pieces[otherKey]);

// Board move keeps local piece coords.
const boardDrop = MoveGeometry.proposeBoardDrop(history.get(), 1, 20, 80);
assert.equal(boardDrop.ok, true);
const hostLocalBefore = history.get().pieces[hostKey].local_x_mm;
next = MoveGeometry.applyBoardMove(history.get(), {
    sheet_no: 1,
    origin_x_mm: boardDrop.origin_x_mm,
    origin_y_mm: boardDrop.origin_y_mm,
});
history.commit(next);
assert.equal(history.get().boards["1"].origin_x_mm, 20);
assert.equal(history.get().pieces[hostKey].local_x_mm, hostLocalBefore);
assert.equal(history.get().boards["1"].user_moved, true);

// Detach guest when dragged out of host hole.
const detach = MoveGeometry.proposePieceDrop(history.get(), guestKey, 20 + 700, 80 + 700);
assert.equal(detach.ok, true);
next = MoveGeometry.applyPieceMove(history.get(), {
    piece_key: guestKey,
    target_sheet_no: detach.target_sheet_no,
    local_x_mm: detach.local_x_mm,
    local_y_mm: detach.local_y_mm,
    delta_x_mm: detach.delta_x_mm,
    delta_y_mm: detach.delta_y_mm,
    detach_host: detach.detach_host,
});
history.commit(next);
assert.equal(history.get().pieces[guestKey].glass_host_key, null);

// Restore entry is undoable.
const dirty = history.get();
assert.notEqual(dirty.boards["1"].origin_x_mm, session.boards["1"].origin_x_mm);
history.restoreEntry();
assert.equal(history.get().boards["1"].origin_x_mm, session.boards["1"].origin_x_mm);
assert.equal(history.get().pieces[hostKey].local_x_mm, session.pieces[hostKey].local_x_mm);
history.undo();
assert.equal(history.get().boards["1"].origin_x_mm, dirty.boards["1"].origin_x_mm);

// Store has no tool mode; interaction is gesture-owned.
const store = createStore({ projection, order_name: "O", plan_name: "P" });
store.attachSession(History.create(session).get(), History.create(session));
assert.equal(store.snapshot().tool, undefined);
assert.equal(typeof store.setTool, "undefined");

// ---------------------------------------------------------------------------
// Cross-frame reframe contract: applyPieceMove without delta_* must still use
// world-space deltas when crossing outside ↔ board or board ↔ board origins.
// ---------------------------------------------------------------------------
{
    function approx(actual, expected, label) {
        assert.ok(
            Math.abs(Number(actual) - Number(expected)) < 0.01,
            `${label}: ${actual} != ${expected}`
        );
    }

    function footprintAligned(piece, label) {
        const fp = MoveGeometry.footprint(piece);
        approx(fp.bounds.x, piece.local_x_mm, `${label} outline.x`);
        approx(fp.bounds.y, piece.local_y_mm, `${label} outline.y`);
    }

    const crossProjection = {
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
                sheet_no: 3,
                full_width_cm: 100,
                full_length_cm: 100,
                applied_trim_width_cm: 0,
                applied_trim_length_cm: 0,
            },
        ],
        pieces: [
            {
                piece_id: 11,
                piece_instance_id: "pi-cross",
                label: "CROSS",
                sheet_no: 1,
                placement_cm: { x: 10, y: 10, w: 20, h: 20 },
            },
            {
                piece_id: 12,
                piece_instance_id: "pi-cross-host",
                label: "CROSS-HOST",
                sheet_no: 1,
                placement_cm: { x: 40, y: 40, w: 40, h: 40 },
                glass_hole_local_mm: [
                    [50, 50],
                    [250, 50],
                    [250, 250],
                    [50, 250],
                ],
            },
            {
                piece_id: 13,
                piece_instance_id: "pi-cross-guest",
                label: "CROSS-GUEST",
                sheet_no: 1,
                placement_cm: { x: 50, y: 50, w: 10, h: 10 },
                glass_host_piece_id: 12,
            },
        ],
        elements: [
            {
                element_id: "cx",
                kind: "finished_outline",
                piece_id: 11,
                piece_instance_id: "pi-cross",
                sheet_no: 1,
                geometry: { outer: [[100, 100], [300, 100], [300, 300], [100, 300]] },
            },
            {
                element_id: "ch",
                kind: "finished_outline",
                piece_id: 12,
                piece_instance_id: "pi-cross-host",
                sheet_no: 1,
                geometry: {
                    outer: [[400, 400], [800, 400], [800, 800], [400, 800]],
                    holes: [[[450, 450], [650, 450], [650, 650], [450, 650]]],
                },
            },
            {
                element_id: "cg",
                kind: "finished_outline",
                piece_id: 13,
                piece_instance_id: "pi-cross-guest",
                sheet_no: 1,
                geometry: { outer: [[500, 500], [600, 500], [600, 600], [500, 600]] },
            },
        ],
    };
    const crossLayout = {
        positions: {
            1: { originX: 0, originY: 36, widthMm: 1000, heightMm: 1000, trimX: 0, trimY: 0 },
            3: { originX: 1400, originY: 80, widthMm: 1000, heightMm: 1000, trimX: 0, trimY: 0 },
        },
    };
    let cross = SessionDocument.buildFromProjection(crossProjection, crossLayout);
    cross.boards["1"].origin_x_mm = 0;
    cross.boards["1"].origin_y_mm = 36;
    cross.boards["3"].origin_x_mm = 1400;
    cross.boards["3"].origin_y_mm = 80;
    const crossKey = "instance:pi-cross";
    const crossHost = "instance:pi-cross-host";
    const crossGuest = "instance:pi-cross-guest";
    const entryPivotBefore = {
        x: cross.pieces[crossKey].entry_pivot_mm.x,
        y: cross.pieces[crossKey].entry_pivot_mm.y,
    };

    // Park piece in world space first (with deltas), then apply without deltas.
    const park = MoveGeometry.proposePieceDrop(cross, crossKey, 3200, 500);
    assert.equal(park.ok, true, park.reason || "park outside");
    cross = MoveGeometry.applyPieceMove(cross, park);
    assert.equal(cross.pieces[crossKey].sheet_no, null);

    // A) outside → board 3 without delta_*
    const toBoard3 = MoveGeometry.applyPieceMove(cross, {
        piece_key: crossKey,
        target_sheet_no: 3,
        local_x_mm: 120,
        local_y_mm: 140,
    });
    assert.notEqual(toBoard3, cross, "outside→board3 must apply");
    assert.equal(toBoard3.pieces[crossKey].sheet_no, 3);
    approx(toBoard3.pieces[crossKey].local_x_mm, 120, "A local_x");
    approx(toBoard3.pieces[crossKey].local_y_mm, 140, "A local_y");
    footprintAligned(toBoard3.pieces[crossKey], "A");
    const worldA = MoveGeometry.worldFootprint(toBoard3.pieces[crossKey], toBoard3.boards);
    approx(worldA.bounds.x, 1400 + 120, "A world.x");
    approx(worldA.bounds.y, 80 + 140, "A world.y");
    approx(toBoard3.pieces[crossKey].pivot_mm.x, 120 + 100, "A pivot.x");
    approx(toBoard3.pieces[crossKey].pivot_mm.y, 140 + 100, "A pivot.y");
    assert.equal(toBoard3.pieces[crossKey].entry_pivot_mm.x, entryPivotBefore.x);
    assert.equal(toBoard3.pieces[crossKey].entry_pivot_mm.y, entryPivotBefore.y);

    // B) board 3 → outside without delta_*
    const toOutside = MoveGeometry.applyPieceMove(toBoard3, {
        piece_key: crossKey,
        target_sheet_no: null,
        local_x_mm: 3500,
        local_y_mm: 600,
    });
    assert.equal(toOutside.pieces[crossKey].sheet_no, null);
    approx(toOutside.pieces[crossKey].local_x_mm, 3500, "B local_x");
    approx(toOutside.pieces[crossKey].local_y_mm, 600, "B local_y");
    footprintAligned(toOutside.pieces[crossKey], "B");
    const worldB = MoveGeometry.worldFootprint(toOutside.pieces[crossKey], toOutside.boards);
    approx(worldB.bounds.x, 3500, "B world.x");
    approx(worldB.bounds.y, 600, "B world.y");

    // C) board 1 → board 3 without delta_*
    let boardHop = SessionDocument.buildFromProjection(crossProjection, crossLayout);
    boardHop.boards["1"].origin_x_mm = 0;
    boardHop.boards["1"].origin_y_mm = 36;
    boardHop.boards["3"].origin_x_mm = 1400;
    boardHop.boards["3"].origin_y_mm = 80;
    const hopC = MoveGeometry.applyPieceMove(boardHop, {
        piece_key: crossKey,
        target_sheet_no: 3,
        local_x_mm: 80,
        local_y_mm: 90,
    });
    assert.equal(hopC.pieces[crossKey].sheet_no, 3);
    approx(hopC.pieces[crossKey].local_x_mm, 80, "C local_x");
    approx(hopC.pieces[crossKey].local_y_mm, 90, "C local_y");
    footprintAligned(hopC.pieces[crossKey], "C");
    const worldC = MoveGeometry.worldFootprint(hopC.pieces[crossKey], hopC.boards);
    approx(worldC.bounds.x, 1400 + 80, "C world.x");
    approx(worldC.bounds.y, 80 + 90, "C world.y");

    // D) board 3 → board 1 without delta_*
    const hopD = MoveGeometry.applyPieceMove(hopC, {
        piece_key: crossKey,
        target_sheet_no: 1,
        local_x_mm: 110,
        local_y_mm: 130,
    });
    assert.equal(hopD.pieces[crossKey].sheet_no, 1);
    approx(hopD.pieces[crossKey].local_x_mm, 110, "D local_x");
    approx(hopD.pieces[crossKey].local_y_mm, 130, "D local_y");
    footprintAligned(hopD.pieces[crossKey], "D");
    const worldD = MoveGeometry.worldFootprint(hopD.pieces[crossKey], hopD.boards);
    approx(worldD.bounds.x, 0 + 110, "D world.x");
    approx(worldD.bounds.y, 36 + 130, "D world.y");

    // E) same-board move without delta_*
    const same = MoveGeometry.applyPieceMove(hopD, {
        piece_key: crossKey,
        target_sheet_no: 1,
        local_x_mm: 200,
        local_y_mm: 220,
    });
    assert.equal(same.pieces[crossKey].sheet_no, 1);
    approx(same.pieces[crossKey].local_x_mm, 200, "E local_x");
    approx(same.pieces[crossKey].local_y_mm, 220, "E local_y");
    footprintAligned(same.pieces[crossKey], "E");
    const worldE = MoveGeometry.worldFootprint(same.pieces[crossKey], same.boards);
    approx(worldE.bounds.x, 200, "E world.x");
    approx(worldE.bounds.y, 36 + 220, "E world.y");

    // F) explicit delta_* wins and must not be recomputed away
    const withDelta = MoveGeometry.proposePieceDrop(same, crossKey, 1400 + 160, 80 + 170);
    assert.equal(withDelta.ok, true);
    assert.equal(withDelta.target_sheet_no, 3);
    const appliedDelta = MoveGeometry.applyPieceMove(same, {
        piece_key: crossKey,
        target_sheet_no: withDelta.target_sheet_no,
        local_x_mm: withDelta.local_x_mm,
        local_y_mm: withDelta.local_y_mm,
        delta_x_mm: withDelta.delta_x_mm,
        delta_y_mm: withDelta.delta_y_mm,
    });
    approx(appliedDelta.pieces[crossKey].local_x_mm, withDelta.local_x_mm, "F local_x");
    approx(appliedDelta.pieces[crossKey].local_y_mm, withDelta.local_y_mm, "F local_y");
    footprintAligned(appliedDelta.pieces[crossKey], "F");
    const worldF = MoveGeometry.worldFootprint(appliedDelta.pieces[crossKey], appliedDelta.boards);
    approx(worldF.bounds.x, 1400 + withDelta.local_x_mm, "F world.x");
    approx(worldF.bounds.y, 80 + withDelta.local_y_mm, "F world.y");

    // Invalid command fails closed (session unchanged).
    const rejected = MoveGeometry.applyPieceMove(same, {
        piece_key: crossKey,
        target_sheet_no: 3,
        local_x_mm: Number.NaN,
        local_y_mm: 100,
    });
    assert.equal(rejected, same);

    // Reject contracts: partial/non-finite deltas, invalid board origin, missing board.
    {
        function assertRejected(label, session, command) {
            const before = JSON.stringify(session);
            const after = MoveGeometry.applyPieceMove(session, command);
            assert.equal(after, session, `${label}: must return same session object`);
            assert.equal(JSON.stringify(after), before, `${label}: session must stay unchanged`);
        }

        assertRejected("partial delta x only", same, {
            piece_key: crossKey,
            target_sheet_no: 3,
            local_x_mm: 50,
            local_y_mm: 60,
            delta_x_mm: 10,
        });
        assertRejected("partial delta y only", same, {
            piece_key: crossKey,
            target_sheet_no: 3,
            local_x_mm: 50,
            local_y_mm: 60,
            delta_y_mm: 10,
        });
        assertRejected("delta NaN", same, {
            piece_key: crossKey,
            target_sheet_no: 3,
            local_x_mm: 50,
            local_y_mm: 60,
            delta_x_mm: Number.NaN,
            delta_y_mm: 10,
        });
        assertRejected("delta Infinity", same, {
            piece_key: crossKey,
            target_sheet_no: 3,
            local_x_mm: 50,
            local_y_mm: 60,
            delta_x_mm: 10,
            delta_y_mm: Number.POSITIVE_INFINITY,
        });
        assertRejected("missing command", same, null);
        assertRejected("missing target board", same, {
            piece_key: crossKey,
            target_sheet_no: 99,
            local_x_mm: 50,
            local_y_mm: 60,
        });

        const badOrigin = JSON.parse(JSON.stringify(same));
        badOrigin.boards["3"].origin_x_mm = "not-a-number";
        assertRejected("invalid target origin", badOrigin, {
            piece_key: crossKey,
            target_sheet_no: 3,
            local_x_mm: 50,
            local_y_mm: 60,
        });
        assertRejected("invalid target origin with deltas", badOrigin, {
            piece_key: crossKey,
            target_sheet_no: 3,
            local_x_mm: 50,
            local_y_mm: 60,
            delta_x_mm: 100,
            delta_y_mm: 20,
        });

        const badSource = JSON.parse(JSON.stringify(same));
        badSource.boards["1"].origin_y_mm = Number.NaN;
        assertRejected("invalid source origin", badSource, {
            piece_key: crossKey,
            target_sheet_no: 3,
            local_x_mm: 50,
            local_y_mm: 60,
        });

        const badTrim = JSON.parse(JSON.stringify(same));
        badTrim.boards["3"].trim_x_mm = Number.POSITIVE_INFINITY;
        assertRejected("invalid target trim", badTrim, {
            piece_key: crossKey,
            target_sheet_no: 3,
            local_x_mm: 50,
            local_y_mm: 60,
        });
    }

    // G) glass host+guest follow the same world delta without delta_*
    let glass = SessionDocument.buildFromProjection(crossProjection, crossLayout);
    glass.boards["1"].origin_x_mm = 0;
    glass.boards["1"].origin_y_mm = 36;
    glass.boards["3"].origin_x_mm = 1400;
    glass.boards["3"].origin_y_mm = 80;
    assert.equal(glass.pieces[crossGuest].glass_host_key, crossHost);
    const hostBefore = MoveGeometry.pieceWorldOrigin(glass, crossHost);
    const guestBefore = MoveGeometry.pieceWorldOrigin(glass, crossGuest);
    const gapX = guestBefore.x - hostBefore.x;
    const gapY = guestBefore.y - hostBefore.y;
    const glassMoved = MoveGeometry.applyPieceMove(glass, {
        piece_key: crossHost,
        target_sheet_no: 3,
        local_x_mm: 100,
        local_y_mm: 110,
    });
    assert.equal(glassMoved.pieces[crossHost].sheet_no, 3);
    assert.equal(glassMoved.pieces[crossGuest].sheet_no, 3);
    assert.equal(glassMoved.pieces[crossGuest].glass_host_key, crossHost);
    footprintAligned(glassMoved.pieces[crossHost], "G host");
    footprintAligned(glassMoved.pieces[crossGuest], "G guest");
    const hostAfter = MoveGeometry.pieceWorldOrigin(glassMoved, crossHost);
    const guestAfter = MoveGeometry.pieceWorldOrigin(glassMoved, crossGuest);
    approx(guestAfter.x - hostAfter.x, gapX, "G gap x");
    approx(guestAfter.y - hostAfter.y, gapY, "G gap y");
    approx(hostAfter.x, 1400 + 100, "G host world.x");
    approx(hostAfter.y, 80 + 110, "G host world.y");
}

console.log("board_editor_session_move.test.js: ok");
