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

const { SessionDocument, MoveGeometry, RotationGeometry, CanvasRenderer } = load();

function projection() {
    const ox = 800;
    const oy = 800;
    const outer = [[ox, oy], [ox + 400, oy], [ox + 400, oy + 600], [ox, oy + 600]];
    const rectHole = [[ox + 40, oy + 40], [ox + 140, oy + 40], [ox + 140, oy + 160], [ox + 40, oy + 160]];
    const circle = Array.from({ length: 8 }, (_, index) => {
        const angle = (Math.PI * 2 * index) / 8;
        return [ox + 280 + 40 * Math.cos(angle), oy + 300 + 40 * Math.sin(angle)];
    });
    return {
        board: { kerf_cm: 0.5 },
        sheets: [{
            sheet_no: 1,
            full_width_cm: 244,
            full_length_cm: 244,
            applied_trim_width_cm: 0,
            applied_trim_length_cm: 0,
        }],
        pieces: [{
            piece_id: 1,
            piece_instance_id: "pi-special",
            label: "SPECIAL",
            sheet_no: 1,
            piece_type: "Special",
            placement_cm: { x: 80, y: 80, w: 40, h: 60 },
            allow_rotation: 1,
            allow_rotation_proven: true,
            geometry_source: "dxf",
        }],
        elements: [{
            element_id: "e-special",
            kind: "finished_outline",
            piece_id: 1,
            piece_instance_id: "pi-special",
            sheet_no: 1,
            geometry: { outer, holes: [rectHole, circle] },
        }],
    };
}

const source = projection();
const layout = CanvasRenderer.sheetLayout(source.sheets, 1);
let session = SessionDocument.buildFromProjection(source, layout);
const piece = session.pieces["instance:pi-special"];
assert.equal(piece.glass_hole_local_mm, null);
assert.equal(piece.opening_rings_mm.length, 2);
assert.equal(piece.base_opening_rings_mm.length, 2);

const origin = MoveGeometry.pieceWorldOrigin(session, "instance:pi-special");
const proposal = MoveGeometry.proposePieceDrop(session, "instance:pi-special", origin.x + 30, origin.y + 40);
assert.equal(proposal.ok, true, proposal.reason || proposal.code || "move");
const before = piece.opening_rings_mm[0][0].slice();
session = MoveGeometry.applyPieceMove(session, proposal);
const moved = session.pieces["instance:pi-special"];
assert.equal(moved.opening_rings_mm.length, 2);
assert.equal(moved.opening_rings_mm[0][0][0], before[0] + proposal.delta_x_mm);
assert.equal(moved.opening_rings_mm[0][0][1], before[1] + proposal.delta_y_mm);
assert.equal(moved.opening_rings_mm[1].length, 8);

const decision = RotationGeometry.validatePieceRotation(session, "instance:pi-special", 90);
assert.equal(decision.ok, true, decision.code || "rotate");
session = RotationGeometry.applyPieceRotation(session, "instance:pi-special", 90);
const rotated = session.pieces["instance:pi-special"];
assert.equal(rotated.rotation_deg, 90);
assert.equal(rotated.opening_rings_mm.length, 2);
assert.equal(rotated.opening_rings_mm[1].length, 8);
assert.notEqual(rotated.opening_rings_mm[0][0][0], moved.opening_rings_mm[0][0][0]);

const renderer = fs.readFileSync(path.join(root, "public/js/board_editor/canvas_renderer.js"), "utf8");
assert.match(renderer, /fill-rule="evenodd"/);
assert.match(renderer, /opening_rings_mm/);

console.log("board_editor_special_openings.test.js: ok");
