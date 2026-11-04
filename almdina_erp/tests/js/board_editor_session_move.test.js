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
            glass_hole_local_mm: [
                [150, 150],
                [250, 150],
                [250, 250],
                [150, 250],
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

console.log("board_editor_session_move.test.js: ok");
