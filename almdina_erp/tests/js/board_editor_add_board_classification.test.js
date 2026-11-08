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
        "public/js/board_editor/rotation_geometry.js",
        "public/js/board_editor/distribution.js",
        "public/js/board_editor/store.js",
    ];
    const context = { __: (message) => message };
    context.window = context;
    context.globalThis = context;
    vm.createContext(context);
    files.forEach((relative) => {
        vm.runInContext(fs.readFileSync(path.join(root, relative), "utf8"), context, { filename: relative });
    });
    return context.window.AlmdinaBoardEditor;
}

const editor = load();
const { History, SessionDocument } = editor;

function projection() {
    return {
        board: {
            full_width_cm: 122,
            full_length_cm: 244,
            usable_width_cm: 120,
            usable_length_cm: 240,
            trim_cm: 1,
            kerf_cm: 0.4,
        },
        sheets: [
            {
                sheet_no: 1,
                resource_kind: "FULL_BOARD",
                full_width_cm: 122,
                full_length_cm: 244,
                applied_trim_width_cm: 1,
                applied_trim_length_cm: 1,
                usable_width_cm: 120,
                usable_length_cm: 240,
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
                piece_instance_id: "pi-a",
                label: "A",
                sheet_no: 1,
                piece_type: "Regular",
                resource_kind: "FULL_BOARD",
                placement_cm: { x: 2, y: 2, w: 40, h: 30 },
                allow_rotation: true,
                allow_rotation_proven: true,
            },
            {
                piece_id: 2,
                piece_instance_id: "pi-b",
                label: "B",
                sheet_no: 1,
                piece_type: "Glass",
                resource_kind: "FULL_BOARD",
                placement_cm: { x: 50, y: 2, w: 20, h: 20 },
                allow_rotation: true,
                allow_rotation_proven: true,
            },
        ],
        elements: [
            {
                kind: "finished_outline",
                piece_instance_id: "pi-a",
                geometry: { outer: [[20, 20], [420, 20], [420, 320], [20, 320]] },
            },
            {
                kind: "finished_outline",
                piece_instance_id: "pi-b",
                geometry: { outer: [[500, 20], [700, 20], [700, 220], [500, 220]] },
            },
        ],
    };
}

function sessionFrom(proj) {
    const layout = {
        positions: {
            1: { originX: 0, originY: 36, widthMm: 1220, heightMm: 2440, trimX: 10, trimY: 10 },
            2: { originX: 1300, originY: 36, widthMm: 400, heightMm: 400, trimX: 0, trimY: 0 },
        },
    };
    return SessionDocument.buildFromProjection(proj, layout);
}

{
    const proj = projection();
    const session = sessionFrom(proj);
    const history = History.create(session);
    const added = SessionDocument.addFullBoard(history.get(), proj);
    assert.equal(added.ok, true);
    assert.equal(added.sheet_no, 3);
    const board = added.session.boards["3"];
    assert.equal(board.width_mm, 1220);
    assert.equal(board.height_mm, 2440);
    assert.equal(board.trim_x_mm, 10);
    assert.equal(board.editor_origin, "full_board");
    assert.notEqual(board.width_mm, 400);
    const second = SessionDocument.addFullBoard(added.session, proj);
    assert.equal(second.sheet_no, 4);
    assert.equal(Object.keys(second.session.boards).sort().join(","), "1,2,3,4");
    history.commit(added.session);
    history.undo();
    assert.equal(history.get().boards["3"], undefined);
    history.redo();
    assert.ok(history.get().boards["3"]);
}

{
    const proj = projection();
    const session = sessionFrom(proj);
    const moved = SessionDocument.clone(session);
    moved.boards["1"].origin_x_mm = 50;
    moved.boards["1"].user_moved = true;
    const before = moved.boards["1"].origin_x_mm;
    const added = SessionDocument.addFullBoard(moved, proj);
    assert.equal(added.session.boards["1"].origin_x_mm, before);
    assert.equal(added.session.boards["1"].user_moved, true);
    assert.ok(added.session.boards["3"].origin_x_mm !== before || added.session.boards["3"].origin_y_mm !== 36);
}

{
    const missing = SessionDocument.addFullBoard(sessionFrom({
        board: { kerf_cm: 0.4 },
        sheets: [],
        pieces: [],
        elements: [],
    }), { board: {}, sheets: [], pieces: [], elements: [] });
    assert.equal(missing.ok, false);
    assert.equal(missing.code, "standard_board_unavailable");
}

{
    const session = sessionFrom(projection());
    const pieceKey = "instance:pi-b";
    assert.equal(session.pieces[pieceKey].piece_type, "Glass");
    assert.equal(session.pieces[pieceKey].resource_kind, "FULL_BOARD");
    const toOffcut = SessionDocument.classifyPiece(session, pieceKey, "OFFCUT", {
        source_party: "FACTORY",
        execution_party: "FACTORY",
    });
    assert.equal(toOffcut.ok, true);
    assert.equal(toOffcut.session.pieces[pieceKey].resource_kind, "OFFCUT");
    assert.equal(toOffcut.session.pieces[pieceKey].piece_type, "Glass");
    assert.equal(
        JSON.stringify(toOffcut.session.pieces[pieceKey].outline_mm),
        JSON.stringify(session.pieces[pieceKey].outline_mm)
    );
    const history = History.create(session);
    history.commit(toOffcut.session);
    history.undo();
    assert.equal(history.get().pieces[pieceKey].resource_kind, "FULL_BOARD");
    history.redo();
    assert.equal(history.get().pieces[pieceKey].resource_kind, "OFFCUT");
    const back = SessionDocument.classifyPiece(toOffcut.session, pieceKey, "FULL_BOARD", {
        source_party: "UNASSIGNED",
        execution_party: "UNASSIGNED",
    });
    assert.equal(back.session.pieces[pieceKey].resource_kind, "FULL_BOARD");
    assert.equal(back.session.pieces[pieceKey].offcut_source_party, "UNASSIGNED");
}

{
    const session = sessionFrom(projection());
    const classified = SessionDocument.classifyPiece(session, "instance:pi-b", "OFFCUT", {
        source_party: "CUSTOMER",
        execution_party: "FACTORY",
    }).session;
    assert.equal(SessionDocument.boardCompositionKind(classified, 1), "mixed");
    const onlyGeometry = SessionDocument.classifyPiece(classified, "instance:pi-b", "FULL_BOARD").session;
    assert.equal(SessionDocument.boardCompositionKind(onlyGeometry, 1), "GEOMETRY");
}

{
    const session = sessionFrom(projection());
    const added = SessionDocument.addFullBoard(session, projection()).session;
    const classified = SessionDocument.classifyPiece(added, "instance:pi-a", "OFFCUT", {
        source_party: "FACTORY",
        execution_party: "FACTORY",
    }).session;
    const exported = SessionDocument.exportLayout(classified);
    assert.equal(exported.boards.some((board) => board.sheet_no === 3 && board.editor_origin === "full_board"), true);
    const pieceA = exported.pieces.find((row) => row.piece_instance_id === "pi-a");
    assert.equal(pieceA.resource_kind, "OFFCUT");
    assert.equal(pieceA.offcut_source_party, "FACTORY");
    const reopened = SessionDocument.applySavedLayout(sessionFrom(projection()), exported);
    assert.equal(reopened.ok, true);
    assert.ok(reopened.session.boards["3"]);
    assert.equal(reopened.session.boards["3"].width_mm, 1220);
    assert.equal(reopened.session.pieces["instance:pi-a"].resource_kind, "OFFCUT");
    assert.equal(reopened.session.pieces["instance:pi-b"].piece_type, "Glass");
}

console.log("board_editor_add_board_classification.test.js: ok");
