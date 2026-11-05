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
        "public/js/board_editor/alignment_geometry.js",
        "public/js/board_editor/store.js",
    ];
    const context = {
        frappe: { utils: { escape_html: (value) => String(value) } },
        __: (message, replace) => {
            if (!Array.isArray(replace) || !replace.length) return message;
            return replace.reduce(
                (text, value, index) => text.replace(`{${index}}`, String(value)),
                message
            );
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

const {
    AlignmentGeometry,
    MoveGeometry,
    SessionDocument,
    History,
    createStore,
} = loadEditor();

assert.ok(AlignmentGeometry);
assert.equal(AlignmentGeometry.MODES.length, 6);

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
            piece_instance_id: "pi-a",
            label: "A",
            sheet_no: 1,
            placement_cm: { x: 1, y: 1, w: 10, h: 8 },
        },
        {
            piece_id: 2,
            piece_instance_id: "pi-b",
            label: "B",
            sheet_no: 1,
            placement_cm: { x: 25, y: 20, w: 10, h: 8 },
        },
        {
            piece_id: 3,
            piece_instance_id: "pi-c",
            label: "C",
            sheet_no: 1,
            placement_cm: { x: 45, y: 40, w: 10, h: 8 },
        },
        {
            piece_id: 4,
            piece_instance_id: "pi-out-a",
            label: "OutA",
            sheet_no: null,
            placement_cm: { x: 0, y: 0, w: 8, h: 8 },
        },
        {
            piece_id: 5,
            piece_instance_id: "pi-out-b",
            label: "OutB",
            sheet_no: null,
            placement_cm: { x: 0, y: 0, w: 8, h: 8 },
        },
        {
            piece_id: 6,
            piece_instance_id: "pi-s2",
            label: "S2",
            sheet_no: 2,
            placement_cm: { x: 1, y: 1, w: 10, h: 10 },
        },
    ],
};

const layout = {
    positions: {
        1: { originX: 0, originY: 0 },
        2: { originX: 1400, originY: 0 },
    },
};

function freshStore() {
    const session = SessionDocument.buildFromProjection(projection, layout);
    // Place outside pieces in world space with separation.
    const outA = Object.values(session.pieces).find((p) => p.piece_instance_id === "pi-out-a");
    const outB = Object.values(session.pieces).find((p) => p.piece_instance_id === "pi-out-b");
    // Keep outside pieces far from board usable areas so resolveDropSheet
    // does not re-attach them during alignment.
    outA.sheet_no = null;
    outA.local_x_mm = -600;
    outA.local_y_mm = 50;
    outA.outline_mm = [[-600, 50], [-520, 50], [-520, 130], [-600, 130]];
    outB.sheet_no = null;
    outB.local_x_mm = -400;
    outB.local_y_mm = 80;
    outB.outline_mm = [[-400, 80], [-320, 80], [-320, 160], [-400, 160]];

    const hist = History.create(session);
    const store = createStore({ projection, order_name: "O", plan_name: "P" });
    store.attachSession(hist.get(), hist);
    return store;
}

function keyByInstance(session, instanceId) {
    return Object.keys(session.pieces).find(
        (key) => session.pieces[key].piece_instance_id === instanceId
    );
}

function applyAlign(store, keys, mode) {
    const proposal = AlignmentGeometry.proposeAlignment(store.snapshot().session, keys, mode);
    if (!proposal.ok) return proposal;
    if (proposal.unchanged) return proposal;
    let next = store.snapshot().session;
    proposal.commands.forEach((command) => {
        next = MoveGeometry.applyPieceMove(next, command);
    });
    store.commitSession(next);
    return { ok: true, unchanged: false };
}

{
    const store = freshStore();
    const session = store.snapshot().session;
    const keyA = keyByInstance(session, "pi-a");
    const keyB = keyByInstance(session, "pi-b");
    assert.equal(AlignmentGeometry.alignmentEligibility(session, [keyA]).enabled, false);
    assert.equal(AlignmentGeometry.alignmentEligibility(session, [keyA, keyB]).enabled, true);
}

{
    const store = freshStore();
    const session = store.snapshot().session;
    const keyA = keyByInstance(session, "pi-a");
    const keyB = keyByInstance(session, "pi-b");
    const beforeA = MoveGeometry.worldFootprint(session.pieces[keyA], session.boards).bounds;
    const beforeB = MoveGeometry.worldFootprint(session.pieces[keyB], session.boards).bounds;
    const groupMinX = Math.min(beforeA.x, beforeB.x);
    assert.equal(applyAlign(store, [keyA, keyB], "align_left").ok, true);
    const after = store.snapshot().session;
    const afterA = MoveGeometry.worldFootprint(after.pieces[keyA], after.boards).bounds;
    const afterB = MoveGeometry.worldFootprint(after.pieces[keyB], after.boards).bounds;
    assert.ok(Math.abs(afterA.x - groupMinX) < 1e-6);
    assert.ok(Math.abs(afterB.x - groupMinX) < 1e-6);
    assert.equal(store.snapshot().canUndo, true);
    store.undo();
    const undone = store.snapshot().session;
    assert.ok(Math.abs(
        MoveGeometry.worldFootprint(undone.pieces[keyB], undone.boards).bounds.x - beforeB.x
    ) < 1e-6);
    store.redo();
    const redone = store.snapshot().session;
    assert.ok(Math.abs(
        MoveGeometry.worldFootprint(redone.pieces[keyB], redone.boards).bounds.x - groupMinX
    ) < 1e-6);
}

{
    const store = freshStore();
    const session = store.snapshot().session;
    const keyA = keyByInstance(session, "pi-a");
    const keyB = keyByInstance(session, "pi-b");
    const beforeA = MoveGeometry.worldFootprint(session.pieces[keyA], session.boards).bounds;
    const beforeB = MoveGeometry.worldFootprint(session.pieces[keyB], session.boards).bounds;
    const groupMaxX = Math.max(beforeA.x + beforeA.w, beforeB.x + beforeB.w);
    assert.equal(applyAlign(store, [keyA, keyB], "align_right").ok, true);
    const after = store.snapshot().session;
    const afterA = MoveGeometry.worldFootprint(after.pieces[keyA], after.boards).bounds;
    const afterB = MoveGeometry.worldFootprint(after.pieces[keyB], after.boards).bounds;
    assert.ok(Math.abs((afterA.x + afterA.w) - groupMaxX) < 1e-6);
    assert.ok(Math.abs((afterB.x + afterB.w) - groupMaxX) < 1e-6);
}

{
    const store = freshStore();
    const session = store.snapshot().session;
    const keyA = keyByInstance(session, "pi-a");
    const keyB = keyByInstance(session, "pi-b");
    const beforeA = MoveGeometry.worldFootprint(session.pieces[keyA], session.boards).bounds;
    const beforeB = MoveGeometry.worldFootprint(session.pieces[keyB], session.boards).bounds;
    const center = (
        Math.min(beforeA.x, beforeB.x)
        + Math.max(beforeA.x + beforeA.w, beforeB.x + beforeB.w)
    ) / 2;
    assert.equal(applyAlign(store, [keyA, keyB], "align_center_x").ok, true);
    const after = store.snapshot().session;
    const afterA = MoveGeometry.worldFootprint(after.pieces[keyA], after.boards).bounds;
    const afterB = MoveGeometry.worldFootprint(after.pieces[keyB], after.boards).bounds;
    assert.ok(Math.abs((afterA.x + afterA.w / 2) - center) < 1e-6);
    assert.ok(Math.abs((afterB.x + afterB.w / 2) - center) < 1e-6);
}

{
    const store = freshStore();
    let session = store.snapshot().session;
    const keyA = keyByInstance(session, "pi-a");
    const keyB = keyByInstance(session, "pi-b");
    // Put B on the same Y band as A so Align Left would overlap / violate kerf.
    const fpA = MoveGeometry.footprint(session.pieces[keyA]);
    const fpB = MoveGeometry.footprint(session.pieces[keyB]);
    const dy = fpA.bounds.y - fpB.bounds.y;
    session.pieces[keyB].local_y_mm = Number(session.pieces[keyB].local_y_mm) + dy;
    if (Array.isArray(session.pieces[keyB].outline_mm)) {
        session.pieces[keyB].outline_mm = session.pieces[keyB].outline_mm.map((pt) => [
            Number(pt[0]),
            Number(pt[1]) + dy,
        ]);
    }
    const hist = History.create(session);
    store.attachSession(hist.get(), hist);
    session = store.snapshot().session;
    const before = JSON.stringify(session.pieces[keyB]);
    const undoBefore = store.snapshot().canUndo;
    const rejected = AlignmentGeometry.proposeAlignment(
        session,
        [keyA, keyB],
        "align_left"
    );
    assert.equal(rejected.ok, false, rejected.reason || "expected collision reject");
    assert.equal(JSON.stringify(store.snapshot().session.pieces[keyB]), before);
    assert.equal(store.snapshot().canUndo, undoBefore);
}

{
    const store = freshStore();
    const session = store.snapshot().session;
    const outA = keyByInstance(session, "pi-out-a");
    const outB = keyByInstance(session, "pi-out-b");
    const beforeA = MoveGeometry.worldFootprint(session.pieces[outA], session.boards).bounds;
    const beforeB = MoveGeometry.worldFootprint(session.pieces[outB], session.boards).bounds;
    const groupMinX = Math.min(beforeA.x, beforeB.x);
    assert.equal(applyAlign(store, [outA, outB], "align_left").ok, true);
    const after = store.snapshot().session;
    assert.equal(after.pieces[outA].sheet_no, null);
    assert.equal(after.pieces[outB].sheet_no, null);
    const afterA = MoveGeometry.worldFootprint(after.pieces[outA], after.boards).bounds;
    const afterB = MoveGeometry.worldFootprint(after.pieces[outB], after.boards).bounds;
    assert.ok(Math.abs(afterA.x - groupMinX) < 1e-6);
    assert.ok(Math.abs(afterB.x - groupMinX) < 1e-6);
}

{
    const store = freshStore();
    const session = store.snapshot().session;
    const keyA = keyByInstance(session, "pi-a");
    const outA = keyByInstance(session, "pi-out-a");
    const keyS2 = keyByInstance(session, "pi-s2");
    assert.equal(
        AlignmentGeometry.alignmentEligibility(session, [keyA, outA]).enabled,
        false
    );
    assert.equal(
        AlignmentGeometry.alignmentEligibility(session, [keyA, keyS2]).enabled,
        false
    );
}

{
    const store = freshStore();
    const session = store.snapshot().session;
    const keyA = keyByInstance(session, "pi-a");
    const keyB = keyByInstance(session, "pi-b");
    session.pieces[keyB].editable = false;
    assert.equal(
        AlignmentGeometry.alignmentEligibility(session, [keyA, keyB]).enabled,
        false
    );
}

{
    const store = freshStore();
    const session = store.snapshot().session;
    const keyA = keyByInstance(session, "pi-a");
    const keyB = keyByInstance(session, "pi-b");
    const before = MoveGeometry.worldFootprint(session.pieces[keyA], session.boards).bounds.y;
    // Already top-aligned after moving B to A's minY via center? Use align_top then unchanged.
    const first = applyAlign(store, [keyA, keyB], "align_top");
    assert.equal(first.ok, true);
    const undoBefore = store.snapshot().canUndo;
    const second = AlignmentGeometry.proposeAlignment(
        store.snapshot().session,
        [keyA, keyB],
        "align_top"
    );
    assert.equal(second.ok, true);
    assert.equal(second.unchanged, true);
    assert.equal(store.snapshot().canUndo, undoBefore);
    assert.ok(Math.abs(
        MoveGeometry.worldFootprint(store.snapshot().session.pieces[keyA], store.snapshot().session.boards).bounds.y
        - before
    ) < 50);
}

function setPieceRect(piece, x, y, w, h) {
    piece.local_x_mm = x;
    piece.local_y_mm = y;
    piece.outline_mm = [
        [x, y],
        [x + w, y],
        [x + w, y + h],
        [x, y + h],
    ];
}

// 1) Unrelated stale board overflow on another sheet must not reject alignment.
{
    const store = freshStore();
    const session = store.snapshot().session;
    const keyA = keyByInstance(session, "pi-a");
    const keyB = keyByInstance(session, "pi-b");
    const keyS2 = keyByInstance(session, "pi-s2");
    setPieceRect(session.pieces[keyS2], 950, 10, 100, 100);
    const hist = History.create(session);
    store.attachSession(hist.get(), hist);
    const live = store.snapshot().session;
    const proposal = AlignmentGeometry.proposeAlignment(
        live,
        [keyA, keyB],
        "align_left"
    );
    assert.equal(proposal.ok, true, proposal.reason || "stale overflow must not block");
    assert.equal(proposal.unchanged, false);
    assert.equal(applyAlign(store, [keyA, keyB], "align_left").ok, true);
}

// 2) Unrelated stale collision on another sheet must not reject alignment.
{
    const store = freshStore();
    const session = store.snapshot().session;
    const keyA = keyByInstance(session, "pi-a");
    const keyB = keyByInstance(session, "pi-b");
    const keyS2 = keyByInstance(session, "pi-s2");
    // Clone S2 into a second overlapping piece on sheet 2.
    const staleA = JSON.parse(JSON.stringify(session.pieces[keyS2]));
    const staleB = JSON.parse(JSON.stringify(session.pieces[keyS2]));
    staleA.piece_instance_id = "pi-stale-a";
    staleB.piece_instance_id = "pi-stale-b";
    setPieceRect(staleA, 20, 20, 80, 80);
    setPieceRect(staleB, 40, 40, 80, 80);
    session.pieces["instance:pi-stale-a"] = staleA;
    session.pieces["instance:pi-stale-b"] = staleB;
    const hist = History.create(session);
    store.attachSession(hist.get(), hist);
    const proposal = AlignmentGeometry.proposeAlignment(
        store.snapshot().session,
        [keyA, keyB],
        "align_left"
    );
    assert.equal(proposal.ok, true, proposal.reason || "stale collision must not block");
}

// 3) New board overflow caused by alignment must reject atomically.
// Pure AABB alignment of on-board roots cannot leave the usable area; a hosted
// guest that extends past its host is the manufacturable overflow case.
{
    const store = freshStore();
    let session = store.snapshot().session;
    const keyA = keyByInstance(session, "pi-a");
    const keyB = keyByInstance(session, "pi-b");
    const keyC = keyByInstance(session, "pi-c");
    setPieceRect(session.pieces[keyA], 100, 40, 100, 100);
    setPieceRect(session.pieces[keyC], 150, 60, 100, 100); // extends past host
    session.pieces[keyC].glass_host_key = keyA;
    setPieceRect(session.pieces[keyB], 950, 40, 50, 50); // right edge at usable limit
    const hist = History.create(session);
    store.attachSession(hist.get(), hist);
    session = store.snapshot().session;
    const before = JSON.stringify(session.pieces);
    const undoBefore = store.snapshot().canUndo;
    const rejected = AlignmentGeometry.proposeAlignment(
        session,
        [keyA, keyC, keyB],
        "align_right"
    );
    assert.equal(rejected.ok, false);
    assert.equal(rejected.code, MoveGeometry.DROP_PARTIAL_BOARD);
    assert.equal(rejected.stage, "final_validation");
    assert.equal(rejected.piece_key, keyC);
    assert.equal(rejected.sheet_no, 1);
    assert.equal(JSON.stringify(store.snapshot().session.pieces), before);
    assert.equal(store.snapshot().canUndo, undoBefore);
}

// 4) New collision with an unselected piece must reject.
{
    const store = freshStore();
    let session = store.snapshot().session;
    const keyA = keyByInstance(session, "pi-a");
    const keyB = keyByInstance(session, "pi-b");
    const keyC = keyByInstance(session, "pi-c");
    // Aligning B left to A would land on C which sits on A's left edge.
    setPieceRect(session.pieces[keyA], 200, 10, 80, 80);
    setPieceRect(session.pieces[keyB], 400, 10, 80, 80);
    setPieceRect(session.pieces[keyC], 200, 10, 80, 80);
    const hist = History.create(session);
    store.attachSession(hist.get(), hist);
    session = store.snapshot().session;
    const before = JSON.stringify(session.pieces);
    const rejected = AlignmentGeometry.proposeAlignment(
        session,
        [keyA, keyB],
        "align_left"
    );
    assert.equal(rejected.ok, false);
    assert.ok(
        rejected.code === MoveGeometry.DROP_OVERLAP || rejected.code === MoveGeometry.DROP_KERF,
        rejected.code
    );
    assert.equal(JSON.stringify(store.snapshot().session.pieces), before);
}

// 5) Kerf clearance violation must reject.
{
    const store = freshStore();
    let session = store.snapshot().session;
    const keyA = keyByInstance(session, "pi-a");
    const keyB = keyByInstance(session, "pi-b");
    const keyC = keyByInstance(session, "pi-c");
    const kerf = Number(session.kerf_mm) || 4;
    setPieceRect(session.pieces[keyA], 100, 10, 80, 80);
    setPieceRect(session.pieces[keyB], 300, 10, 80, 80);
    // Unselected C sits just left of A's left edge with gap < kerf after B aligns left.
    setPieceRect(session.pieces[keyC], 100 - 80 - (kerf / 2), 10, 80, 80);
    const hist = History.create(session);
    store.attachSession(hist.get(), hist);
    session = store.snapshot().session;
    const rejected = AlignmentGeometry.proposeAlignment(
        session,
        [keyA, keyB],
        "align_left"
    );
    assert.equal(rejected.ok, false);
    assert.equal(rejected.code, MoveGeometry.DROP_KERF, rejected.code);
}

// 6) Exact usable edge remains accepted; tiny real overflow rejects.
{
    const store = freshStore();
    let session = store.snapshot().session;
    const keyA = keyByInstance(session, "pi-a");
    const keyB = keyByInstance(session, "pi-b");
    const usableW = Number(session.boards["1"].usable_width_mm);
    setPieceRect(session.pieces[keyA], usableW - 80, 20, 80, 60);
    setPieceRect(session.pieces[keyB], 40, 200, 80, 60);
    let hist = History.create(session);
    store.attachSession(hist.get(), hist);
    const exact = AlignmentGeometry.proposeAlignment(
        store.snapshot().session,
        [keyA, keyB],
        "align_right"
    );
    assert.equal(exact.ok, true, exact.reason || "exact edge must accept");

    session = store.snapshot().session;
    setPieceRect(session.pieces[keyA], usableW - 80 + 0.02, 20, 80, 60);
    setPieceRect(session.pieces[keyB], 40, 200, 80, 60);
    hist = History.create(session);
    store.attachSession(hist.get(), hist);
    const overflow = AlignmentGeometry.proposeAlignment(
        store.snapshot().session,
        [keyA, keyB],
        "align_right"
    );
    assert.equal(overflow.ok, false);
    assert.equal(overflow.code, MoveGeometry.DROP_PARTIAL_BOARD);
}

// 7) Special L polygons: AABB may overlap while material stays clear → accept.
{
    const store = freshStore();
    let session = store.snapshot().session;
    const keyA = keyByInstance(session, "pi-a");
    const keyB = keyByInstance(session, "pi-b");
    const keyC = keyByInstance(session, "pi-c");
    // L pocket; unselected so alignment of B/C only collides via final/drop checks.
    session.pieces[keyA].outline_mm = [
        [10, 10], [210, 10], [210, 90], [90, 90], [90, 210], [10, 210],
    ];
    session.pieces[keyA].local_x_mm = 10;
    session.pieces[keyA].local_y_mm = 10;
    setPieceRect(session.pieces[keyB], 94, 400, 80, 80);
    setPieceRect(session.pieces[keyC], 300, 94, 20, 20);
    const hist = History.create(session);
    store.attachSession(hist.get(), hist);
    session = store.snapshot().session;
    const nested = AlignmentGeometry.proposeAlignment(
        session,
        [keyB, keyC],
        "align_top"
    );
    assert.equal(nested.ok, true, nested.reason || "L nesting alignment must accept");
    let trial = session;
    nested.commands.forEach((command) => {
        trial = MoveGeometry.applyPieceMove(trial, command);
    });
    const fpL = MoveGeometry.footprint(trial.pieces[keyA]);
    const fpB = MoveGeometry.footprint(trial.pieces[keyB]);
    const aabbOverlap = !(
        fpB.bounds.x + fpB.bounds.w <= fpL.bounds.x
        || fpL.bounds.x + fpL.bounds.w <= fpB.bounds.x
        || fpB.bounds.y + fpB.bounds.h <= fpL.bounds.y
        || fpL.bounds.y + fpL.bounds.h <= fpB.bounds.y
    );
    assert.equal(aabbOverlap, true, "nested piece AABB overlaps L bounds");
    assert.equal(
        MoveGeometry.pairConflict(fpL, fpB, trial.kerf_mm || 0),
        null,
        "material polygons must stay clear"
    );

    // Same axis move into the L solid body must still reject.
    setPieceRect(session.pieces[keyB], 20, 400, 60, 60);
    setPieceRect(session.pieces[keyC], 300, 20, 20, 20);
    const solid = AlignmentGeometry.proposeAlignment(
        session,
        [keyB, keyC],
        "align_top"
    );
    assert.equal(solid.ok, false);
    assert.equal(solid.code, MoveGeometry.DROP_OVERLAP);
}

// 8) Host/guest: guest rides with host; link preserved; no double move.
{
    const store = freshStore();
    let session = store.snapshot().session;
    const keyA = keyByInstance(session, "pi-a");
    const keyB = keyByInstance(session, "pi-b");
    const keyC = keyByInstance(session, "pi-c");
    setPieceRect(session.pieces[keyA], 40, 40, 120, 120);
    setPieceRect(session.pieces[keyC], 60, 60, 40, 40);
    session.pieces[keyC].glass_host_key = keyA;
    // Keep B on a clear Y band so align-left does not collide with the guest.
    setPieceRect(session.pieces[keyB], 300, 220, 80, 80);
    const hist = History.create(session);
    store.attachSession(hist.get(), hist);
    session = store.snapshot().session;
    const guestBefore = MoveGeometry.footprint(session.pieces[keyC]).bounds;
    const hostBefore = MoveGeometry.footprint(session.pieces[keyA]).bounds;
    const relative = {
        x: guestBefore.x - hostBefore.x,
        y: guestBefore.y - hostBefore.y,
    };
    const proposal = AlignmentGeometry.proposeAlignment(
        session,
        [keyA, keyC, keyB],
        "align_left"
    );
    assert.equal(proposal.ok, true, proposal.reason || "host/guest align");
    assert.ok(!proposal.commands.some((c) => c.piece_key === keyC), "guest is not a root command");
    proposal.commands.forEach((command) => {
        session = MoveGeometry.applyPieceMove(session, command);
    });
    assert.equal(session.pieces[keyC].glass_host_key, keyA);
    const guestAfter = MoveGeometry.footprint(session.pieces[keyC]).bounds;
    const hostAfter = MoveGeometry.footprint(session.pieces[keyA]).bounds;
    assert.ok(Math.abs((guestAfter.x - hostAfter.x) - relative.x) < 1e-6);
    assert.ok(Math.abs((guestAfter.y - hostAfter.y) - relative.y) < 1e-6);
}

// 9) Outside alignment ignores unrelated on-board overflow and stays outside.
{
    const store = freshStore();
    const session = store.snapshot().session;
    const outA = keyByInstance(session, "pi-out-a");
    const outB = keyByInstance(session, "pi-out-b");
    const keyS2 = keyByInstance(session, "pi-s2");
    setPieceRect(session.pieces[keyS2], 950, 10, 100, 100);
    const hist = History.create(session);
    store.attachSession(hist.get(), hist);
    const live = store.snapshot().session;
    assert.equal(applyAlign(store, [outA, outB], "align_left").ok, true);
    const after = store.snapshot().session;
    assert.equal(after.pieces[outA].sheet_no, null);
    assert.equal(after.pieces[outB].sheet_no, null);
    // Prove final validation itself ignores the stale overflow for outside scope.
    const finalOk = AlignmentGeometry.validateFinalSession(
        after,
        new Set([outA, outB]),
        "outside"
    );
    assert.equal(finalOk.ok, true);
}

// 10) Atomicity: reject leaves session/history/selection untouched; success is one undo step.
{
    const store = freshStore();
    let session = store.snapshot().session;
    const keyA = keyByInstance(session, "pi-a");
    const keyB = keyByInstance(session, "pi-b");
    const keyC = keyByInstance(session, "pi-c");
    setPieceRect(session.pieces[keyA], 100, 40, 100, 100);
    setPieceRect(session.pieces[keyC], 150, 60, 100, 100);
    session.pieces[keyC].glass_host_key = keyA;
    setPieceRect(session.pieces[keyB], 950, 40, 50, 50);
    const hist = History.create(session);
    store.attachSession(hist.get(), hist);
    session = store.snapshot().session;
    const fingerprint = JSON.stringify(session);
    const undoBefore = store.snapshot().canUndo;
    const rejected = AlignmentGeometry.proposeAlignment(
        session,
        [keyA, keyC, keyB],
        "align_right"
    );
    assert.equal(rejected.ok, false);
    assert.equal(JSON.stringify(store.snapshot().session), fingerprint);
    assert.equal(store.snapshot().canUndo, undoBefore);

    const okStore = freshStore();
    const okSession = okStore.snapshot().session;
    const okA = keyByInstance(okSession, "pi-a");
    const okB = keyByInstance(okSession, "pi-b");
    const applied = applyAlign(okStore, [okA, okB], "align_left");
    assert.equal(applied.ok, true);
    assert.equal(okStore.snapshot().canUndo, true);
    const afterAlign = JSON.stringify(okStore.snapshot().session.pieces[okB]);
    okStore.undo();
    assert.notEqual(JSON.stringify(okStore.snapshot().session.pieces[okB]), afterAlign);
    okStore.redo();
    assert.equal(JSON.stringify(okStore.snapshot().session.pieces[okB]), afterAlign);
}

const css = fs.readFileSync(path.join(root, "public/css/board_editor.css"), "utf8");
const page = fs.readFileSync(path.join(root, "almdina_erp/page/board_editor/board_editor.js"), "utf8");
const controller = fs.readFileSync(path.join(root, "public/js/board_editor/controller.js"), "utf8");
const right = fs.readFileSync(path.join(root, "public/js/board_editor/right_sidebar_renderer.js"), "utf8");
const canvas = fs.readFileSync(path.join(root, "public/js/board_editor/canvas_renderer.js"), "utf8");
const arCsv = fs.readFileSync(path.join(root, "translations/ar.csv"), "utf8");

assert.match(css, /--abe-right-sidebar-width:\s*240px/);
assert.match(css, /grid-template-areas:\s*"sidebar canvas inspector"/);
assert.doesNotMatch(css, /\.abe-right-sidebar\s*\{[^}]*grid-template-rows:\s*minmax\(0,\s*1fr\)\s+auto/);
assert.match(page, /alignment_geometry\.js\?v=2/);
assert.match(page, /right_sidebar_renderer\.js\?v=4/);
assert.match(page, /board_editor\.css\?v=36/);
assert.match(controller, /RightSidebarRenderer/);
assert.match(controller, /applyAlignment/);
assert.match(right, /data-abe-align/);
assert.match(right, /data-abe-position-bar/);
assert.match(right, /alignmentSectionHtml\(storeView\)[\s\S]*propertiesSectionHtml\(storeView\)/);
assert.doesNotMatch(canvas, /data-abe-position-bar/);
assert.match(canvas, /abe-float-tools/);
[
    "Piece properties",
    "Alignment",
    "Align left",
    "Align pieces on the same board only, or pieces outside all boards.",
].forEach((key) => {
    assert.ok(arCsv.includes(key), `missing ar.csv key: ${key}`);
});

// Alignment icons stay mounted for every selection state; only disabled toggles.
{
    function inspectorHost() {
        return {
            __html: "",
            set innerHTML(value) { this.__html = String(value); },
            get innerHTML() { return this.__html; },
            querySelector() {
                return {
                    querySelectorAll: () => [],
                    querySelector: () => null,
                    addEventListener() {},
                };
            },
            querySelectorAll() { return []; },
        };
    }
    function loadUi() {
        const files = [
            "public/js/board_editor/history.js",
            "public/js/board_editor/session_document.js",
            "public/js/board_editor/move_geometry.js",
            "public/js/board_editor/position_geometry.js",
            "public/js/board_editor/alignment_geometry.js",
            "public/js/board_editor/right_sidebar_renderer.js",
        ];
        const context = {
            frappe: { utils: { escape_html: (value) => String(value) } },
            __: (message) => message,
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
    const ui = loadUi();
    const session = SessionDocument.buildFromProjection(projection, layout);
    const keyA = keyByInstance(session, "pi-a");
    const keyB = keyByInstance(session, "pi-b");
    function paint(keys) {
        const host = inspectorHost();
        ui.RightSidebarRenderer.render(host, {
            session,
            selectedPieceKeys: keys,
        }, {});
        return host.innerHTML;
    }
    const emptyHtml = paint([]);
    const oneHtml = paint([keyA]);
    const twoHtml = paint([keyA, keyB]);
    assert.equal((emptyHtml.match(/data-abe-align="/g) || []).length, 6);
    assert.equal((oneHtml.match(/data-abe-align="/g) || []).length, 6);
    assert.equal((twoHtml.match(/data-abe-align="/g) || []).length, 6);
    assert.match(emptyHtml, /data-abe-align="align_left"[^>]*\sdisabled(?:\s|>)/);
    assert.match(oneHtml, /data-abe-align="align_left"[^>]*\sdisabled(?:\s|>)/);
    assert.match(twoHtml, /data-abe-align="align_left"[^>]*aria-disabled="false"/);
    assert.doesNotMatch(twoHtml, /data-abe-align="align_left"[^>]*\sdisabled(?:\s|>)/);
    const alignAt = emptyHtml.indexOf('data-abe-align-section="1"');
    const propsAt = emptyHtml.indexOf("abe-inspector-props-block");
    assert.ok(alignAt >= 0 && propsAt > alignAt, "alignment must stack above properties");
}

console.log("board_editor_alignment.test.js: ok");
