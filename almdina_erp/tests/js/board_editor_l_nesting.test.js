"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.resolve(__dirname, "../..");

function loadGeometry() {
    const files = [
        "public/js/board_editor/move_geometry.js",
        "public/js/board_editor/rotation_geometry.js",
        "public/js/board_editor/transform_geometry.js",
        "public/js/board_editor/canvas_renderer.js",
    ];
    const context = {
        frappe: {
            utils: {
                escape_html: (value) => String(value == null ? "" : value),
                icon: (name) => `<svg data-icon="${name}"></svg>`,
            },
        },
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

const {
    MoveGeometry,
    TransformGeometry,
    RotationGeometry,
    CanvasRenderer,
} = loadGeometry();

const L_OUTLINE = [[0, 0], [1000, 0], [1000, 400], [400, 400], [400, 1000], [0, 1000]];

function boardSession(extraPieces = {}, kerfMm = 4) {
    const lPiece = {
        piece_key: "instance:l",
        piece_instance_id: "l",
        piece_id: 10,
        piece_type: "L-Shaped Corner",
        editable: true,
        allow_rotation: true,
        allow_rotation_proven: true,
        distribution: "active",
        sheet_no: 1,
        rotation_deg: 0,
        flip_h: false,
        flip_v: false,
        mirrored: false,
        local_x_mm: 0,
        local_y_mm: 0,
        base_outline_mm: L_OUTLINE.map((p) => p.slice()),
        outline_mm: L_OUTLINE.map((p) => p.slice()),
        pivot_mm: { x: 500, y: 500 },
        machining_paths: [],
        glass_host_key: null,
    };
    return {
        pieces: {
            "instance:l": lPiece,
            ...extraPieces,
        },
        boards: {
            1: {
                sheet_no: 1,
                origin_x_mm: 0,
                origin_y_mm: 36,
                trim_x_mm: 0,
                trim_y_mm: 0,
                width_mm: 2800,
                height_mm: 2100,
                usable_width_mm: 2800,
                usable_length_mm: 2100,
                title_band_mm: 36,
            },
        },
        kerf_mm: kerfMm,
        machine_type: "CNC Router",
        stale_cut_path_sheets: [],
        stale_unbound_text_sheets: [],
    };
}

function rectGuest(localX, localY, size = 300) {
    const outline = [
        [localX, localY],
        [localX + size, localY],
        [localX + size, localY + size],
        [localX, localY + size],
    ];
    return {
        piece_key: "instance:g",
        piece_instance_id: "g",
        piece_id: 11,
        piece_type: "Regular",
        editable: true,
        allow_rotation: true,
        allow_rotation_proven: true,
        distribution: "active",
        sheet_no: 1,
        rotation_deg: 0,
        flip_h: false,
        flip_v: false,
        mirrored: false,
        local_x_mm: localX,
        local_y_mm: localY,
        base_outline_mm: outline.map((p) => p.slice()),
        outline_mm: outline.map((p) => p.slice()),
        pivot_mm: { x: localX + size / 2, y: localY + size / 2 },
        machining_paths: [],
        glass_host_key: null,
    };
}

{
    const guest = rectGuest(430, 430, 300);
    guest.sheet_no = null;
    guest.local_x_mm = 2000;
    guest.local_y_mm = 2000;
    guest.outline_mm = [[2000, 2000], [2300, 2000], [2300, 2300], [2000, 2300]];
    guest.base_outline_mm = guest.outline_mm.map((p) => p.slice());
    const session = boardSession({ "instance:g": guest }, 4);
    const ok = MoveGeometry.validatePieceDrop(session, "instance:g", 430, 36 + 430);
    assert.equal(ok.ok, true, JSON.stringify(ok));
    assert.equal(ok.sheet_no, 1);
}

{
    const guest = rectGuest(2000, 2000, 300);
    guest.sheet_no = null;
    const session = boardSession({ "instance:g": guest }, 4);
    const bad = MoveGeometry.validatePieceDrop(session, "instance:g", 402, 36 + 402);
    assert.equal(bad.ok, false);
    assert.equal(bad.code, "kerf_clearance");
}

{
    const guest = rectGuest(2000, 2000, 300);
    guest.sheet_no = null;
    const session = boardSession({ "instance:g": guest }, 4);
    const bad = MoveGeometry.validatePieceDrop(session, "instance:g", 200, 36 + 200);
    assert.equal(bad.ok, false);
    assert.equal(bad.code, "piece_overlap");
}

{
    const a = rectGuest(430, 430, 200);
    const b = rectGuest(660, 660, 200);
    b.piece_key = "instance:h";
    b.piece_instance_id = "h";
    b.piece_id = 12;
    assert.equal(
        MoveGeometry.pairConflict(MoveGeometry.footprint(a), MoveGeometry.footprint(b), 4),
        null
    );
    const session = boardSession({ "instance:g": a }, 4);
    assert.equal(
        MoveGeometry.pairConflict(
            MoveGeometry.footprint(session.pieces["instance:l"]),
            MoveGeometry.footprint(a),
            4
        ),
        null
    );
}

{
    const guest = rectGuest(430, 430, 300);
    const session = boardSession({ "instance:g": guest }, 4);
    const bad = MoveGeometry.validatePieceDrop(session, "instance:l", 200, 36 + 200);
    assert.equal(bad.ok, false);
    assert.ok(["piece_overlap", "kerf_clearance"].includes(bad.code), bad.code);
}

{
    const blocked = boardSession({ "instance:g": rectGuest(450, 450, 300) }, 4);
    const decision = TransformGeometry.applyAngleMirror(blocked, "instance:l");
    assert.equal(decision.ok, false);
    assert.ok(["piece_overlap", "kerf_clearance"].includes(decision.code), decision.code);

    const far = rectGuest(1600, 100, 100);
    const allowedSession = boardSession({ "instance:g": far }, 4);
    const allowed = TransformGeometry.applyAngleMirror(allowedSession, "instance:l");
    assert.equal(allowed.ok, true, JSON.stringify(allowed));
    assert.equal(allowed.session.pieces["instance:l"].mirrored, true);
}

{
    const session = boardSession({}, 4);
    const decision = RotationGeometry.validatePieceRotation(session, "instance:l", 90);
    assert.equal(decision.ok, true, JSON.stringify(decision));
}

{
    const guest = rectGuest(450, 450, 300);
    const session = boardSession({ "instance:g": guest }, 4);
    const unsafe = RotationGeometry.validatePieceRotation(session, "instance:l", 180);
    assert.equal(unsafe.ok, false);
    assert.ok(["piece_overlap", "kerf_clearance"].includes(unsafe.code), unsafe.code);
}

{
    const mid = CanvasRenderer.leftOuterEdgeMidpoint(L_OUTLINE);
    assert.ok(mid);
    assert.ok(Math.abs(mid.x - 0) < 1e-6);
    assert.ok(Math.abs(mid.y - 500) < 1e-6);

    const mirrored = L_OUTLINE.map(([x, y]) => [1000 - x, y]);
    const midAfter = CanvasRenderer.leftOuterEdgeMidpoint(mirrored);
    assert.ok(midAfter);
    assert.ok(midAfter.x < 500);
}

{
    const source = fs.readFileSync(
        path.join(root, "public/js/board_editor/canvas_renderer.js"),
        "utf8"
    );
    assert.match(source, /data-abe-angle-mirror/);
    assert.match(source, /lCornerMirrorControlSvg/);
    assert.match(source, /handlers\.mirrorAngle/);
    assert.match(source, /abe-l-mirror-btn/);
    const css = fs.readFileSync(path.join(root, "public/css/board_editor.css"), "utf8");
    assert.match(css, /\.abe-l-mirror-btn/);
    const catalog = fs.readFileSync(path.join(root, "translations/ar.csv"), "utf8");
    assert.match(catalog, /Mirror angle,انعكاس الزاوية/);
    assert.match(catalog, /Pieces would overlap/);
    assert.match(catalog, /Kerf clearance is insufficient/);
}

console.log("board editor L-cutout nesting + mirror chrome passed");
