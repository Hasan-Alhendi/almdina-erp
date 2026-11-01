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
        "public/js/board_editor/store.js",
    ];
    const context = {
        frappe: { utils: { escape_html: (value) => String(value) } },
        __: (message) => message,
    };
    context.window = context;
    context.globalThis = context;
    vm.createContext(context);
    files.forEach((relative) => {
        vm.runInContext(fs.readFileSync(path.join(root, relative), "utf8"), context);
    });
    return context.window.AlmdinaBoardEditor;
}

function rect(x, y, w, h) {
    return [[x, y], [x + w, y], [x + w, y + h], [x, y + h]];
}

function piece(key, opts) {
    const x = opts.x;
    const y = opts.y;
    const w = opts.w;
    const h = opts.h;
    const outline = opts.outline || rect(x, y, w, h);
    return {
        piece_key: key,
        piece_id: opts.piece_id,
        piece_instance_id: key.replace(/^instance:/, ""),
        sheet_no: 1,
        local_x_mm: x,
        local_y_mm: y,
        placement_cm: { x: x / 10, y: y / 10, w: w / 10, h: h / 10, rotated: false },
        outline_mm: outline,
        base_outline_mm: outline.map((row) => row.slice()),
        pivot_mm: { x: x + w / 2, y: y + h / 2 },
        entry_pivot_mm: { x: x + w / 2, y: y + h / 2 },
        rotation_deg: 0,
        editable: opts.editable !== false,
        allow_rotation: opts.allow !== false,
        allow_rotation_proven: true,
        glass_host_key: opts.host || null,
        glass_hole_local_mm: opts.hole || null,
        base_hole_mm: opts.hole ? opts.hole.map((row) => row.slice()) : null,
        piece_type: opts.piece_type || "Regular",
        apply_rotated_to_geometry: false,
        source_orientation_applied: true,
        source_rotated_dims: Boolean(opts.source_rotated_dims),
    };
}

function baseSession(pieces) {
    return {
        boards: {
            1: {
                sheet_no: 1,
                origin_x_mm: 0,
                origin_y_mm: 36,
                width_mm: 2000,
                height_mm: 2000,
                trim_x_mm: 0,
                trim_y_mm: 0,
                usable_width_mm: 2000,
                usable_length_mm: 2000,
                title_band_mm: 36,
            },
        },
        pieces,
        kerf_mm: 4,
        stale_cut_path_sheets: [],
        stale_unbound_text_sheets: [],
    };
}

const editor = load();
const { RotationGeometry, MoveGeometry, SnapGeometry, History } = editor;

{
    let session = baseSession({
        "instance:a": piece("instance:a", { piece_id: 1, x: 100, y: 100, w: 200, h: 100 }),
        "instance:b": piece("instance:b", { piece_id: 2, x: 600, y: 100, w: 80, h: 80 }),
    });
    const decision = RotationGeometry.validatePieceRotation(session, "instance:a", 37);
    assert.equal(decision.ok, true);
    session = RotationGeometry.applyPieceRotation(session, "instance:a", 37);
    assert.equal(RotationGeometry.anglesEquivalent(session.pieces["instance:a"].rotation_deg, 37), true);

    const history = History.create(session);
    const before = MoveGeometry.pieceWorldOrigin(session, "instance:a");
    const proposal = MoveGeometry.proposePieceDrop(session, "instance:a", before.x + 40, before.y + 20);
    assert.equal(proposal.ok, true);
    session = MoveGeometry.applyPieceMove(session, proposal);
    history.commit(session);
    assert.equal(RotationGeometry.anglesEquivalent(session.pieces["instance:a"].rotation_deg, 37), true);

    const fp = MoveGeometry.footprint(session.pieces["instance:a"]);
    assert.equal(fp.kind, "polygon");
    assert.ok(fp.points.length >= 4);

    const snap = SnapGeometry.suggestPieceSnap(
        session,
        "instance:a",
        MoveGeometry.pieceWorldOrigin(session, "instance:a").x,
        MoveGeometry.pieceWorldOrigin(session, "instance:a").y,
        { magnetEnabled: true, thresholdMm: 20, exitThresholdMm: 30, activeSnap: null }
    );
    assert.ok(snap == null || typeof snap.ok === "boolean");

    const undone = history.undo();
    assert.equal(RotationGeometry.anglesEquivalent(undone.pieces["instance:a"].rotation_deg, 37), true);
    const restored = history.restoreEntry();
    assert.equal(RotationGeometry.anglesEquivalent(restored.pieces["instance:a"].rotation_deg, 37), true);
}

assert.equal(RotationGeometry.normalizeAngleDeg(360), 0);
assert.equal(RotationGeometry.anglesEquivalent(0, 360), true);
{
    let session = baseSession({
        "instance:a": piece("instance:a", { piece_id: 1, x: 200, y: 200, w: 100, h: 80 }),
    });
    session = RotationGeometry.applyPieceRotation(session, "instance:a", 350);
    const around = RotationGeometry.validatePieceRotation(session, "instance:a", 10);
    assert.equal(around.ok, true);
    const noop = RotationGeometry.validatePieceRotation(session, "instance:a", 710);
    assert.equal(noop.ok, true);
    assert.equal(noop.noop, true);
}

{
    const host = piece("instance:host", {
        piece_id: 1,
        x: 100,
        y: 100,
        w: 400,
        h: 400,
        hole: rect(150, 150, 200, 200),
    });
    const guest = piece("instance:guest", {
        piece_id: 2,
        x: 180,
        y: 180,
        w: 60,
        h: 60,
        host: "instance:host",
    });
    const nested = piece("instance:nested", {
        piece_id: 3,
        x: 190,
        y: 190,
        w: 20,
        h: 20,
        host: "instance:guest",
    });
    let session = baseSession({
        "instance:host": host,
        "instance:guest": guest,
        "instance:nested": nested,
    });
    assert.equal(RotationGeometry.validatePieceRotation(session, "instance:host", 25).ok, true);
    session = RotationGeometry.applyPieceRotation(session, "instance:host", 25);
    assert.equal(RotationGeometry.anglesEquivalent(session.pieces["instance:guest"].rotation_deg, 25), true);
    assert.equal(RotationGeometry.anglesEquivalent(session.pieces["instance:nested"].rotation_deg, 25), true);
    assert.equal(session.pieces["instance:guest"].glass_host_key, "instance:host");

    session.pieces["instance:guest"].allow_rotation = false;
    const blocked = RotationGeometry.pieceRotationEligibility(session, "instance:host");
    assert.equal(blocked.rotatable, false);
    assert.equal(blocked.reason, "guest_rotation_forbidden");
}

{
    const outline = rect(40, 40, 120, 60);
    const row = piece("instance:dxf", {
        piece_id: 8,
        x: 40,
        y: 40,
        w: 120,
        h: 60,
        source_rotated_dims: true,
    });
    row.placement_cm.rotated = true;
    row.outline_mm = outline.map((point) => point.slice());
    row.base_outline_mm = outline.map((point) => point.slice());
    const session = baseSession({ "instance:dxf": row });
    const next = RotationGeometry.applyPieceRotation(session, "instance:dxf", 12);
    assert.equal(next.pieces["instance:dxf"].base_outline_mm.length, outline.length);
    next.pieces["instance:dxf"].base_outline_mm.forEach((point, index) => {
        assert.ok(Math.abs(point[0] - outline[index][0]) < 1e-9);
        assert.ok(Math.abs(point[1] - outline[index][1]) < 1e-9);
    });
    assert.equal(next.pieces["instance:dxf"].apply_rotated_to_geometry, false);
    outline.forEach((point, index) => {
        const expected = RotationGeometry.rotatePoint(point, row.pivot_mm, 12);
        assert.ok(Math.abs(next.pieces["instance:dxf"].outline_mm[index][0] - expected[0]) < 1e-6);
        assert.ok(Math.abs(next.pieces["instance:dxf"].outline_mm[index][1] - expected[1]) < 1e-6);
    });
}

{
    const a = piece("instance:a", { piece_id: 1, x: 100, y: 300, w: 220, h: 16 });
    const b = piece("instance:b", { piece_id: 2, x: 400, y: 100, w: 16, h: 220 });
    const session = baseSession({ "instance:a": a, "instance:b": b });
    const decision = RotationGeometry.validatePieceRotation(session, "instance:a", 90);
    assert.equal(decision.ok, true);
}

console.log("board_editor_rotation.test.js: ok");
