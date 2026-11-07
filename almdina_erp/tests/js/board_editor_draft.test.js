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
const { History, SessionDocument, MoveGeometry, RotationGeometry, Distribution, createStore } = editor;

function projection() {
    return {
        board: { kerf_cm: 0.4, width_cm: 122, length_cm: 244 },
        sheets: [
            {
                sheet_no: 1,
                full_width_cm: 122,
                full_length_cm: 244,
                applied_trim_width_cm: 0,
                applied_trim_length_cm: 0,
                usable_width_cm: 122,
                usable_length_cm: 244,
            },
            {
                sheet_no: 2,
                full_width_cm: 80,
                full_length_cm: 80,
                applied_trim_width_cm: 0,
                applied_trim_length_cm: 0,
                usable_width_cm: 80,
                usable_length_cm: 80,
            },
        ],
        pieces: [
            {
                piece_id: 11,
                piece_instance_id: "pi-move",
                label: "MOVE",
                sheet_no: 1,
                placement_cm: { x: 70, y: 80, w: 20, h: 20 },
                allow_rotation: true,
                allow_rotation_proven: true,
            },
            {
                piece_id: 1,
                piece_instance_id: "pi-host",
                label: "HOST",
                sheet_no: 1,
                placement_cm: { x: 10, y: 10, w: 40, h: 30 },
                glass_hole_local_mm: [[50, 50], [150, 50], [150, 150], [50, 150]],
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
                piece_id: 4,
                piece_instance_id: "pi-board",
                label: "BOARD",
                sheet_no: 2,
                placement_cm: { x: 2, y: 2, w: 10, h: 10 },
            },
        ],
        elements: [],
        layers: [{ match_key: "GEOMETRY" }],
    };
}

function sessionFrom(source) {
    return SessionDocument.buildFromProjection(source || projection(), { positions: {} });
}

function pieceById(session, instance) {
    return Object.values(session.pieces).find((piece) => piece.piece_instance_id === instance);
}

const source = projection();
let working = sessionFrom(source);
const mover = pieceById(working, "pi-move");
working = MoveGeometry.applyPieceMove(working, {
    piece_key: mover.piece_key,
    local_x_mm: mover.local_x_mm + 30,
    local_y_mm: mover.local_y_mm + 12,
    sheet_no: mover.sheet_no,
    delta_x_mm: 30,
    delta_y_mm: 12,
});
const rotated = RotationGeometry.applyPieceRotation(working, pieceById(working, "pi-move").piece_key, 15);
assert.ok(Math.abs(pieceById(rotated, "pi-move").rotation_deg - 15) < 0.01);
working = rotated;
const host = pieceById(working, "pi-host");
const hostBefore = host.local_x_mm;
working = MoveGeometry.applyPieceMove(working, {
    piece_key: host.piece_key,
    local_x_mm: host.local_x_mm + 20,
    local_y_mm: host.local_y_mm,
    sheet_no: host.sheet_no,
    delta_x_mm: 20,
    delta_y_mm: 0,
});
assert.equal(pieceById(working, "pi-guest").glass_host_piece_id, 1);
assert.ok(pieceById(working, "pi-host").local_x_mm > hostBefore);

const posed = SessionDocument.applySavedLayout(sessionFrom(source), SessionDocument.exportLayout(working));
assert.equal(posed.ok, true);
assert.ok(Math.abs(pieceById(posed.session, "pi-move").rotation_deg - 15) < 0.01);
assert.equal(pieceById(posed.session, "pi-guest").glass_host_piece_id, 1);
assert.equal(pieceById(posed.session, "pi-host").glass_host_piece_id, null);
assert.ok(Math.abs(pieceById(posed.session, "pi-host").local_x_mm - pieceById(working, "pi-host").local_x_mm) < 0.01);
assert.equal(
    SessionDocument.distributionFingerprint(posed.session),
    SessionDocument.distributionFingerprint(working)
);

const outside = MoveGeometry.applyPieceMove(working, {
    piece_key: pieceById(working, "pi-move").piece_key,
    local_x_mm: 2000,
    local_y_mm: 40,
    sheet_no: null,
    delta_x_mm: 2000 - pieceById(working, "pi-move").local_x_mm,
    delta_y_mm: 0,
});
let distributed = Distribution.excludePiece(
    outside,
    pieceById(outside, "pi-guest").piece_key
).session;
distributed = Distribution.removeBoard(distributed, 2).session;
assert.equal(distributed.boards["2"], undefined);
assert.equal(pieceById(distributed, "pi-board").sheet_no, null);
assert.equal(pieceById(distributed, "pi-guest").distribution, "excluded");
assert.equal(pieceById(distributed, "pi-move").sheet_no, null);

const saved = SessionDocument.exportLayout(distributed);
const reopened = SessionDocument.applySavedLayout(sessionFrom(source), saved);
assert.equal(reopened.ok, true);
const again = reopened.session;
assert.equal(pieceById(again, "pi-move").sheet_no, null);
assert.ok(Math.abs(pieceById(again, "pi-move").rotation_deg - 15) < 0.01);
assert.equal(pieceById(again, "pi-host").glass_host_piece_id, null);
assert.equal(pieceById(again, "pi-guest").distribution, "excluded");
assert.equal(pieceById(again, "pi-guest").glass_host_piece_id, null);
assert.equal(again.boards["2"], undefined);
assert.equal(pieceById(again, "pi-board").sheet_no, null);
assert.equal(
    SessionDocument.distributionFingerprint(again),
    SessionDocument.distributionFingerprint(distributed)
);

const history = History.create(again);
assert.equal(history.state().canUndo, false);
history.undo();
assert.equal(
    SessionDocument.distributionFingerprint(history.get()),
    SessionDocument.distributionFingerprint(again)
);

const store = createStore({ projection: source, capabilities: { edit_layout: true } });
store.attachSession(sessionFrom(source), History.create(sessionFrom(source)));
store.noteDraftBaseline({
    draftVersion: 0,
    savedFingerprint: SessionDocument.distributionFingerprint(store.snapshot().session),
    canSaveLayout: true,
});
const clean = SessionDocument.distributionFingerprint(store.snapshot().session);
store.setViewport({ scale: 2, scrollX: 40, scrollY: 80, userAdjusted: true });
store.setLayerVisible("GEOMETRY", false);
store.selectPiece(11, { pieceKey: pieceById(store.snapshot().session, "pi-move").piece_key });
assert.equal(store.snapshot().distributionDirty, false);
assert.equal(SessionDocument.distributionFingerprint(store.snapshot().session), clean);

store.commitSession(working);
assert.equal(store.snapshot().distributionDirty, true);
const sent = clean;
const settled = SessionDocument.settleDraftSave(
    store.snapshot(),
    sent,
    { ok: true, draft_version: 1 }
);
assert.equal(settled.saveState, "dirty");
assert.equal(settled.session, store.snapshot().session);
const failed = SessionDocument.settleDraftSave(store.snapshot(), sent, null);
assert.equal(failed.saveState, "failed");
assert.equal(failed.saveConflictCode, null);
assert.equal(failed.session, store.snapshot().session);
assert.equal(
    SessionDocument.distributionFingerprint(failed.session),
    SessionDocument.distributionFingerprint(store.snapshot().session)
);

const versionConflict = SessionDocument.settleDraftSave(
    store.snapshot(),
    sent,
    { ok: false, code: "version_conflict", current_draft_version: 4 }
);
assert.equal(versionConflict.saveState, "conflict");
assert.equal(versionConflict.saveConflictCode, "version_conflict");
assert.equal(
    SessionDocument.distributionFingerprint(versionConflict.session),
    SessionDocument.distributionFingerprint(store.snapshot().session)
);

const sourceConflict = SessionDocument.settleDraftSave(
    store.snapshot(),
    sent,
    { ok: false, code: "source_conflict", current_draft_version: 4 }
);
assert.equal(sourceConflict.saveState, "conflict");
assert.equal(sourceConflict.saveConflictCode, "source_conflict");

const schemaError = SessionDocument.settleDraftSave(
    store.snapshot(),
    sent,
    { ok: false, code: "invalid_layout", reason: "forbidden_field" }
);
assert.equal(schemaError.saveState, "failed");
assert.equal(schemaError.saveConflictCode, null);

const canvasSource = fs.readFileSync(
    path.join(root, "public/js/board_editor/canvas_renderer.js"),
    "utf8"
);
assert.match(canvasSource, /A newer draft was saved\. Your local edits are still here\./);
assert.match(canvasSource, /The source cutting plan data changed\. Your local edits are still here\./);
assert.match(canvasSource, /saveConflictCode/);

const reviewStore = createStore({ projection: source, capabilities: { edit_layout: true } });
const reviewSession = sessionFrom(source);
reviewStore.attachSession(reviewSession, History.create(reviewSession));
reviewStore.noteDraftBaseline({
    draftVersion: 1,
    savedFingerprint: SessionDocument.distributionFingerprint(reviewSession),
    canSaveLayout: true,
});
const reviewRequest = reviewStore.beginReview();
assert.ok(reviewRequest);
assert.equal(reviewStore.snapshot().reviewInFlight, true);
const reviewResponse = {
    ready: true,
    draft_version: 1,
    distribution_fingerprint: reviewRequest.fingerprint,
    issues: [],
};
const kept = SessionDocument.settleReview(reviewStore.snapshot(), reviewRequest, reviewResponse);
assert.equal(kept.ignored, false);
assert.equal(kept.failed, false);
reviewStore.settleReview(reviewRequest, reviewResponse);
assert.equal(reviewStore.snapshot().review.ready, true);

reviewStore.setViewport({ scale: 3, scrollX: 12, scrollY: 8, userAdjusted: true });
reviewStore.setLayerVisible("GEOMETRY", false);
assert.equal(reviewStore.snapshot().review.ready, true);

const stale = SessionDocument.settleReview(
    reviewStore.snapshot(),
    { serial: reviewRequest.serial, fingerprint: "old", draftVersion: 1 },
    reviewResponse
);
assert.equal(stale.ignored, true);

const beforeMove = SessionDocument.distributionFingerprint(reviewStore.snapshot().session);
const reviewMover = pieceById(reviewStore.snapshot().session, "pi-move");
const moved = MoveGeometry.applyPieceMove(reviewStore.snapshot().session, {
    piece_key: reviewMover.piece_key,
    local_x_mm: reviewMover.local_x_mm + 5,
    local_y_mm: reviewMover.local_y_mm,
    sheet_no: reviewMover.sheet_no,
    delta_x_mm: 5,
    delta_y_mm: 0,
});
reviewStore.commitSession(moved);
assert.notEqual(
    SessionDocument.distributionFingerprint(reviewStore.snapshot().session),
    beforeMove
);
assert.equal(reviewStore.snapshot().review, null);
assert.equal(reviewStore.snapshot().reviewStale, true);
const ignoredLate = SessionDocument.settleReview(
    reviewStore.snapshot(),
    reviewRequest,
    reviewResponse
);
assert.equal(ignoredLate.ignored, true);
assert.equal(
    SessionDocument.distributionFingerprint(ignoredLate.session),
    SessionDocument.distributionFingerprint(reviewStore.snapshot().session)
);

const page = fs.readFileSync(
    path.join(root, "almdina_erp/page/board_editor/board_editor.js"),
    "utf8"
);
const controller = fs.readFileSync(path.join(root, "public/js/board_editor/controller.js"), "utf8");
assert.match(page, /applySavedDraft/);
assert.match(page, /!== "source"/);
assert.match(controller, /beforeunload/);
assert.match(controller, /saveDraft/);
assert.match(controller, /reviewDraft/);
assert.match(controller, /installLeaveGuards/);
assert.match(controller, /distributionDirty/);
assert.match(
    fs.readFileSync(path.join(root, "public/js/board_editor/api.js"), "utf8"),
    /validate_board_editor_draft/
);

console.log("board editor draft contract passed");
