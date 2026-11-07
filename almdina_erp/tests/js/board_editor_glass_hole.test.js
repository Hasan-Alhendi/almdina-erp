"use strict";

/**
 * Glass opening coordinate contract for Board Editor sessions.
 * Manufacturing glass_hole_local_mm is piece-local; session outline is usable-sheet.
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
    ];
    const context = {
        frappe: { utils: { escape_html: (value) => String(value) } },
        __: (message) => message,
        console,
    };
    context.window = context;
    context.globalThis = context;
    vm.createContext(context);
    files.forEach((relative) => {
        vm.runInContext(fs.readFileSync(path.join(root, relative), "utf8"), context);
    });
    return context.window.AlmdinaBoardEditor;
}

const { SessionDocument, MoveGeometry, CanvasRenderer, RotationGeometry } = load();

function glassProjection({
    xCm = 50,
    yCm = 80,
    wCm = 80,
    hCm = 80,
    holeLocal = [[50, 50], [750, 50], [750, 750], [50, 750]],
    includeGeometryHoles = true,
    fullWidthCm = 244,
    fullLengthCm = 244,
} = {}) {
    const ox = xCm * 10;
    const oy = yCm * 10;
    const w = wCm * 10;
    const h = hCm * 10;
    const outer = [[ox, oy], [ox + w, oy], [ox + w, oy + h], [ox, oy + h]];
    const placedHole = holeLocal.map((point) => [point[0] + ox, point[1] + oy]);
    return {
        board: { kerf_cm: 0.4 },
        sheets: [{
            sheet_no: 1,
            full_width_cm: fullWidthCm,
            full_length_cm: fullLengthCm,
            applied_trim_width_cm: 0,
            applied_trim_length_cm: 0,
        }],
        pieces: [{
            piece_id: 1,
            piece_instance_id: "pi-glass",
            label: "GLASS",
            sheet_no: 1,
            piece_type: "Glass",
            placement_cm: { x: xCm, y: yCm, w: wCm, h: hCm },
            glass_hole_local_mm: holeLocal.map((row) => row.slice()),
            geometry_source: includeGeometryHoles ? "placement_with_glass_hole" : "placement_box",
        }],
        elements: [{
            element_id: "e-glass",
            kind: "finished_outline",
            piece_id: 1,
            piece_instance_id: "pi-glass",
            sheet_no: 1,
            geometry: {
                outer,
                holes: includeGeometryHoles ? [placedHole] : [],
            },
        }],
    };
}

function holeBounds(points) {
    const xs = points.map((point) => Number(point[0]));
    const ys = points.map((point) => Number(point[1]));
    return {
        x: Math.min(...xs),
        y: Math.min(...ys),
        w: Math.max(...xs) - Math.min(...xs),
        h: Math.max(...ys) - Math.min(...ys),
    };
}

function assertHoleInsideOutline(hole, outline, label) {
    const hb = holeBounds(hole);
    const ob = holeBounds(outline);
    assert.ok(hb.x >= ob.x - 1e-6, `${label}: hole.minX`);
    assert.ok(hb.y >= ob.y - 1e-6, `${label}: hole.minY`);
    assert.ok(hb.x + hb.w <= ob.x + ob.w + 1e-6, `${label}: hole.maxX`);
    assert.ok(hb.y + hb.h <= ob.y + ob.h + 1e-6, `${label}: hole.maxY`);
}

// Reproduction: piece-local manufacturing hole must become usable-sheet in session.
{
    const projection = glassProjection();
    const layout = CanvasRenderer.sheetLayout(projection.sheets, 1);
    const session = SessionDocument.buildFromProjection(projection, layout);
    const piece = session.pieces["instance:pi-glass"];
    assert.ok(piece);
    assert.equal(piece.local_x_mm, 500);
    assert.equal(piece.local_y_mm, 800);
    assert.equal(piece.outline_mm[0][0], 500);
    assert.equal(piece.outline_mm[0][1], 800);
    // Expected usable-sheet hole = placement origin + piece-local ring.
    assert.equal(piece.glass_hole_local_mm[0][0], 550);
    assert.equal(piece.glass_hole_local_mm[0][1], 850);
    assert.equal(piece.glass_hole_local_mm[2][0], 1250);
    assert.equal(piece.glass_hole_local_mm[2][1], 1550);
    assert.equal(piece.base_hole_mm[0][0], 550);
    assert.equal(piece.base_hole_mm[0][1], 850);
    assertHoleInsideOutline(piece.glass_hole_local_mm, piece.outline_mm, "session");
}

// Without geometry.holes, still place piece-local ring into usable-sheet frame.
{
    const projection = glassProjection({ includeGeometryHoles: false });
    const layout = CanvasRenderer.sheetLayout(projection.sheets, 1);
    const session = SessionDocument.buildFromProjection(projection, layout);
    const piece = session.pieces["instance:pi-glass"];
    assert.equal(piece.glass_hole_local_mm[0][0], 550);
    assert.equal(piece.glass_hole_local_mm[0][1], 850);
    assertHoleInsideOutline(piece.glass_hole_local_mm, piece.outline_mm, "no-geom-holes");
}

// Prefer authoritative geometry.holes (already usable-sheet); do not double-offset.
{
    const projection = glassProjection();
    // Corrupt piece-local field to prove geometry.holes wins.
    projection.pieces[0].glass_hole_local_mm = [[1, 1], [2, 1], [2, 2], [1, 2]];
    const layout = CanvasRenderer.sheetLayout(projection.sheets, 1);
    const session = SessionDocument.buildFromProjection(projection, layout);
    const piece = session.pieces["instance:pi-glass"];
    assert.equal(piece.glass_hole_local_mm[0][0], 550);
    assert.equal(piece.glass_hole_local_mm[0][1], 850);
}

// Move keeps hole nested with the same relative offset.
{
    const projection = glassProjection();
    const layout = CanvasRenderer.sheetLayout(projection.sheets, 1);
    let session = SessionDocument.buildFromProjection(projection, layout);
    const key = "instance:pi-glass";
    const before = session.pieces[key];
    const rel = [
        before.glass_hole_local_mm[0][0] - before.outline_mm[0][0],
        before.glass_hole_local_mm[0][1] - before.outline_mm[0][1],
    ];
    const proposal = MoveGeometry.proposeGroupMove(session, [key], 100, 50);
    assert.equal(proposal.ok, true, proposal.reason || "move");
    proposal.commands.forEach((command) => {
        session = MoveGeometry.applyPieceMove(session, command);
    });
    const after = session.pieces[key];
    assert.equal(after.outline_mm[0][0], before.outline_mm[0][0] + 100);
    assert.equal(after.outline_mm[0][1], before.outline_mm[0][1] + 50);
    assert.equal(after.glass_hole_local_mm[0][0], after.outline_mm[0][0] + rel[0]);
    assert.equal(after.glass_hole_local_mm[0][1], after.outline_mm[0][1] + rel[1]);
    assertHoleInsideOutline(after.glass_hole_local_mm, after.outline_mm, "after-move");
}

// Rotation keeps hole and outline sharing one pivot frame.
{
    const projection = glassProjection();
    const layout = CanvasRenderer.sheetLayout(projection.sheets, 1);
    const session = SessionDocument.buildFromProjection(projection, layout);
    const piece = session.pieces["instance:pi-glass"];
    piece.allow_rotation = true;
    piece.allow_rotation_proven = true;
    RotationGeometry.ensureBaseGeometry(piece);
    piece.rotation_deg = 90;
    RotationGeometry.rederiveOutline(piece);
    assertHoleInsideOutline(piece.glass_hole_local_mm, piece.outline_mm, "after-rotate");
}

// Draft reopen rebuilds from projection then reframes — no double hole offset.
{
    const projection = glassProjection();
    const layout = CanvasRenderer.sheetLayout(projection.sheets, 1);
    let session = SessionDocument.buildFromProjection(projection, layout);
    const key = "instance:pi-glass";
    const proposal = MoveGeometry.proposeGroupMove(session, [key], 100, 50);
    assert.equal(proposal.ok, true, proposal.reason || "draft-move");
    proposal.commands.forEach((command) => {
        session = MoveGeometry.applyPieceMove(session, command);
    });
    const saved = SessionDocument.exportLayout(session);
    const rebuilt = SessionDocument.buildFromProjection(projection, layout);
    const applied = SessionDocument.applySavedLayout(rebuilt, saved);
    assert.equal(applied.ok, true, applied.code || "apply");
    const piece = applied.session.pieces[key];
    assert.equal(piece.local_x_mm, 600);
    assert.equal(piece.local_y_mm, 850);
    assert.equal(piece.glass_hole_local_mm[0][0], 650);
    assert.equal(piece.glass_hole_local_mm[0][1], 900);
    assertHoleInsideOutline(piece.glass_hole_local_mm, piece.outline_mm, "draft-reopen");
}

// Host/guest: hole usable-sheet frame keeps guest nested; group move shifts both once.
{
    const projection = glassProjection();
    projection.pieces.push({
        piece_id: 2,
        piece_instance_id: "pi-guest",
        label: "GUEST",
        sheet_no: 1,
        placement_cm: { x: 60, y: 90, w: 20, h: 20 },
        glass_host_piece_id: 1,
    });
    projection.elements.push({
        element_id: "e-guest",
        kind: "finished_outline",
        piece_id: 2,
        piece_instance_id: "pi-guest",
        sheet_no: 1,
        geometry: {
            outer: [[600, 900], [800, 900], [800, 1100], [600, 1100]],
        },
    });
    const layout = CanvasRenderer.sheetLayout(projection.sheets, 1);
    let session = SessionDocument.buildFromProjection(projection, layout);
    const hostKey = "instance:pi-glass";
    const guestKey = "instance:pi-guest";
    assert.equal(session.pieces[guestKey].glass_host_key, hostKey);
    assertHoleInsideOutline(
        session.pieces[guestKey].outline_mm,
        session.pieces[hostKey].glass_hole_local_mm,
        "guest-in-hole"
    );
    const guestRel = [
        session.pieces[guestKey].local_x_mm - session.pieces[hostKey].local_x_mm,
        session.pieces[guestKey].local_y_mm - session.pieces[hostKey].local_y_mm,
    ];
    const proposal = MoveGeometry.proposeGroupMove(session, [hostKey], 100, 50);
    assert.equal(proposal.ok, true, proposal.reason || "host-guest-move");
    assert.equal(proposal.commands.length, 1);
    assert.equal(proposal.commands[0].piece_key, hostKey);
    // Guest rides with host inside applyPieceMove (single delta, no second command).
    session = MoveGeometry.applyPieceMove(session, proposal.commands[0]);
    assert.equal(session.pieces[guestKey].glass_host_key, hostKey);
    assert.equal(
        session.pieces[guestKey].local_x_mm - session.pieces[hostKey].local_x_mm,
        guestRel[0]
    );
    assert.equal(
        session.pieces[guestKey].local_y_mm - session.pieces[hostKey].local_y_mm,
        guestRel[1]
    );
    assertHoleInsideOutline(
        session.pieces[guestKey].outline_mm,
        session.pieces[hostKey].glass_hole_local_mm,
        "guest-in-hole-after-move"
    );
}

{
    const page = fs.readFileSync(path.join(root, "almdina_erp/page/board_editor/board_editor.js"), "utf8");
    assert.match(page, /session_document\.js\?v=23/);
    const source = fs.readFileSync(path.join(root, "public/js/board_editor/session_document.js"), "utf8");
    assert.match(source, /resolveSessionHoleMm|usableSheetHoleFromPieceLocal/);
}

console.log("board_editor_glass_hole.test.js: ok");
