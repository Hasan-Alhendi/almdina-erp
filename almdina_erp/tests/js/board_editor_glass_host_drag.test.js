"use strict";

/**
 * Glass host/guest drag: reject material overlap, allow safe re-entry to trusted host.
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

const { SessionDocument, MoveGeometry, History, CanvasRenderer } = load();

function rect(x, y, w, h) {
    return [[x, y], [x + w, y], [x + w, y + h], [x, y + h]];
}

function glassFixture() {
    // Host 1000×1000 at (100,100); hole usable-sheet (200,200)-(1000,1000).
    // Guest 300×300 at (300,300) inside the opening.
    return {
        board: { kerf_cm: 0.4 },
        sheets: [{
            sheet_no: 1,
            full_width_cm: 200,
            full_length_cm: 200,
            applied_trim_width_cm: 0,
            applied_trim_length_cm: 0,
        }],
        pieces: [
            {
                piece_id: 1,
                piece_instance_id: "pi-host",
                label: "HOST",
                sheet_no: 1,
                piece_type: "Glass",
                placement_cm: { x: 10, y: 10, w: 100, h: 100 },
                glass_hole_local_mm: rect(100, 100, 800, 800),
            },
            {
                piece_id: 2,
                piece_instance_id: "pi-guest",
                label: "GUEST",
                sheet_no: 1,
                placement_cm: { x: 30, y: 30, w: 30, h: 30 },
                glass_host_piece_id: 1,
            },
            {
                piece_id: 3,
                piece_instance_id: "pi-other",
                label: "OTHER",
                sheet_no: 1,
                placement_cm: { x: 70, y: 70, w: 15, h: 15 },
                glass_host_piece_id: 1,
            },
        ],
        elements: [
            {
                kind: "finished_outline",
                piece_instance_id: "pi-host",
                geometry: {
                    outer: rect(100, 100, 1000, 1000),
                    holes: [rect(200, 200, 800, 800)],
                },
            },
            {
                kind: "finished_outline",
                piece_instance_id: "pi-guest",
                geometry: { outer: rect(300, 300, 300, 300) },
            },
            {
                kind: "finished_outline",
                piece_instance_id: "pi-other",
                geometry: { outer: rect(700, 700, 150, 150) },
            },
        ],
    };
}

function buildSession() {
    const projection = glassFixture();
    const layout = CanvasRenderer.sheetLayout(projection.sheets, 1);
    const session = SessionDocument.buildFromProjection(projection, layout);
    session.kerf_mm = 4;
    return session;
}

const hostKey = "instance:pi-host";
const guestKey = "instance:pi-guest";
const otherKey = "instance:pi-other";

// A: move fully inside the opening — accept, keep host.
{
    const session = buildSession();
    assert.equal(session.pieces[guestKey].glass_host_key, hostKey);
    assert.equal(session.pieces[guestKey].source_glass_host_key, hostKey);
    const origin = MoveGeometry.pieceWorldOrigin(session, guestKey);
    const proposal = MoveGeometry.proposePieceDrop(
        session,
        guestKey,
        origin.x + 40,
        origin.y + 20
    );
    assert.equal(proposal.ok, true, proposal.reason || "inside-move");
    assert.equal(proposal.detach_host, false);
    const next = MoveGeometry.applyPieceMove(session, proposal);
    assert.equal(next.pieces[guestKey].glass_host_key, hostKey);
    assert.equal(next.pieces[guestKey].local_x_mm, session.pieces[guestKey].local_x_mm + 40);
}

// B: partial exit onto glass material — reject without mutation.
{
    const history = History.create(buildSession());
    const before = history.get();
    const guest = before.pieces[guestKey];
    // Shift left so guest straddles hole wall at x=200 (guest was 300..600).
    const origin = MoveGeometry.pieceWorldOrigin(before, guestKey);
    const proposal = MoveGeometry.proposePieceDrop(
        before,
        guestKey,
        origin.x - 150,
        origin.y
    );
    assert.equal(proposal.ok, false, "partial material exit must reject");
    assert.equal(proposal.code, MoveGeometry.DROP_OVERLAP);
    assert.deepEqual(history.get().pieces[guestKey], before.pieces[guestKey]);
    assert.equal(history.get().pieces[guestKey].glass_host_key, hostKey);
    assert.equal(guest.local_x_mm, before.pieces[guestKey].local_x_mm);
}

// C: lost relationship — re-enter trusted host opening and restore link.
{
    let session = buildSession();
    session.pieces[guestKey].glass_host_key = null;
    session.pieces[guestKey].glass_host_piece_id = null;
    assert.equal(session.pieces[guestKey].source_glass_host_key, hostKey);
    // Park guest outside the host first (free board space).
    const parked = MoveGeometry.proposePieceDrop(session, guestKey, 1200, 36 + 200);
    assert.equal(parked.ok, true, parked.reason || "park");
    session = MoveGeometry.applyPieceMove(session, {
        ...parked,
        detach_host: true,
    });
    assert.equal(session.pieces[guestKey].glass_host_key, null);
    // Return fully into the opening.
    const reenter = MoveGeometry.proposePieceDrop(session, guestKey, 0 + 350, 36 + 350);
    assert.equal(reenter.ok, true, reenter.reason || "reenter");
    assert.equal(reenter.attach_host_key, hostKey);
    session = MoveGeometry.applyPieceMove(session, reenter);
    assert.equal(session.pieces[guestKey].glass_host_key, hostKey);
    assert.equal(session.pieces[guestKey].glass_host_piece_id, 1);
}

// D: two guests — kerf / overlap between them still enforced.
{
    const session = buildSession();
    const origin = MoveGeometry.pieceWorldOrigin(session, guestKey);
    const other = session.pieces[otherKey];
    const proposal = MoveGeometry.proposePieceDrop(
        session,
        guestKey,
        0 + other.local_x_mm,
        36 + other.local_y_mm
    );
    assert.equal(proposal.ok, false);
    assert.ok(
        proposal.code === MoveGeometry.DROP_OVERLAP || proposal.code === MoveGeometry.DROP_KERF,
        proposal.code
    );
    assert.equal(origin.x + 0, origin.x);
}

// Forged host: cannot attach to a non-source host just by sitting in its hole.
{
    const session = buildSession();
    // Fabricate a second glass host without declaring guest's source for it.
    session.pieces["instance:pi-fake"] = {
        ...session.pieces[hostKey],
        piece_key: "instance:pi-fake",
        piece_id: 99,
        piece_instance_id: "pi-fake",
        local_x_mm: 1100,
        local_y_mm: 100,
        outline_mm: rect(1100, 100, 1000, 1000),
        glass_hole_local_mm: rect(1200, 200, 800, 800),
        glass_host_key: null,
        source_glass_host_key: null,
    };
    session.pieces[guestKey].glass_host_key = null;
    session.pieces[guestKey].glass_host_piece_id = null;
    const intoFake = MoveGeometry.proposePieceDrop(session, guestKey, 0 + 1300, 36 + 400);
    assert.equal(intoFake.ok, true, intoFake.reason || "fake-nest-material");
    assert.equal(intoFake.attach_host_key == null, true);
    const next = MoveGeometry.applyPieceMove(session, intoFake);
    assert.equal(next.pieces[guestKey].glass_host_key, null);
}

{
    const page = fs.readFileSync(path.join(root, "almdina_erp/page/board_editor/board_editor.js"), "utf8");
    assert.match(page, /move_geometry\.js\?v=21/);
    assert.match(page, /session_document\.js\?v=24/);
}

console.log("board_editor_glass_host_drag.test.js: ok");
