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
        "public/js/board_editor/transform_geometry.js",
        "public/js/board_editor/store.js",
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

const {
    History,
    SessionDocument,
    RotationGeometry,
    TransformGeometry,
} = load();

function rectPiece(overrides = {}) {
    return {
        piece_key: "instance:a",
        piece_instance_id: "pi-a",
        piece_id: 1,
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
        local_x_mm: 100,
        local_y_mm: 120,
        base_outline_mm: [[100, 120], [140, 120], [140, 180], [100, 180]],
        outline_mm: [[100, 120], [140, 120], [140, 180], [100, 180]],
        pivot_mm: { x: 120, y: 150 },
        machining_paths: [],
        ...overrides,
    };
}

function sessionFor(piece) {
    return {
        pieces: { [piece.piece_key]: piece },
        boards: {
            1: {
                sheet_no: 1,
                origin_x_mm: 0,
                origin_y_mm: 0,
                trim_x_mm: 0,
                trim_y_mm: 0,
                usable_width_mm: 2800,
                usable_length_mm: 2100,
            },
        },
        kerf_mm: 0,
        machine_type: "CNC Router",
        stale_cut_path_sheets: [],
        stale_unbound_text_sheets: [],
    };
}

function nextAnglePairTarget(currentDeg, firstDeg, secondDeg) {
    const current = RotationGeometry.normalizeAngleDeg(currentDeg);
    if (RotationGeometry.anglesEquivalent(current, firstDeg)) {
        return RotationGeometry.normalizeAngleDeg(secondDeg);
    }
    if (RotationGeometry.anglesEquivalent(current, secondDeg)) {
        return RotationGeometry.normalizeAngleDeg(firstDeg);
    }
    return RotationGeometry.normalizeAngleDeg(firstDeg);
}

// +30° uses the same angle path normalization as the angle field.
{
    let angle = 0;
    angle = RotationGeometry.normalizeAngleDeg(angle + 30);
    assert.equal(angle, 30);
    angle = RotationGeometry.normalizeAngleDeg(angle + 30);
    assert.equal(angle, 60);
    angle = RotationGeometry.normalizeAngleDeg(angle + 30);
    assert.equal(angle, 90);
    assert.equal(RotationGeometry.normalizeAngleDeg(45 + 30), 75);
}

// Fixed angle-pair toggles: 0↔180 and 90↔270; other angles snap to the pair first.
{
    assert.equal(nextAnglePairTarget(0, 0, 180), 180);
    assert.equal(nextAnglePairTarget(180, 0, 180), 0);
    assert.equal(nextAnglePairTarget(30, 0, 180), 0);
    assert.equal(nextAnglePairTarget(90, 90, 270), 270);
    assert.equal(nextAnglePairTarget(270, 90, 270), 90);
    assert.equal(nextAnglePairTarget(30, 90, 270), 90);

    const history = History.create(sessionFor(rectPiece({ rotation_deg: 30 })));
    const first = RotationGeometry.applyPieceRotation(history.get(), "instance:a", nextAnglePairTarget(30, 0, 180));
    history.commit(first);
    assert.ok(RotationGeometry.anglesEquivalent(history.get().pieces["instance:a"].rotation_deg, 0));
    assert.equal(history.get().pieces["instance:a"].flip_h, false);

    const second = RotationGeometry.applyPieceRotation(history.get(), "instance:a", nextAnglePairTarget(0, 0, 180));
    history.commit(second);
    assert.ok(RotationGeometry.anglesEquivalent(history.get().pieces["instance:a"].rotation_deg, 180));

    history.undo();
    assert.ok(RotationGeometry.anglesEquivalent(history.get().pieces["instance:a"].rotation_deg, 0));
    history.redo();
    assert.ok(RotationGeometry.anglesEquivalent(history.get().pieces["instance:a"].rotation_deg, 180));
}

// Angle mirror remains one undo step and keeps selection-oriented geometry parity.
{
    const piece = rectPiece({ piece_type: "Clipped Corner", rotation_deg: 45 });
    const history = History.create(sessionFor(piece));
    const mirrored = TransformGeometry.applyAngleMirror(history.get(), "instance:a");
    assert.equal(mirrored.ok, true);
    history.commit(mirrored.session);
    assert.equal(history.get().pieces["instance:a"].mirrored, true);
    history.undo();
    assert.equal(history.get().pieces["instance:a"].mirrored, false);
}

// Layout export/import keeps transform parity; legacy rows open without extra mirror.
{
    const piece = rectPiece({ piece_type: "L-Shaped Corner", mirrored: true, flip_h: true, rotation_deg: 30 });
    const session = sessionFor(piece);
    const layout = SessionDocument.exportLayout(session);
    assert.equal(layout.pieces[0].mirrored, true);
    assert.equal(layout.pieces[0].flip_h, true);
    assert.equal(layout.pieces[0].flip_v, false);

    const fresh = sessionFor(rectPiece({ piece_type: "L-Shaped Corner" }));
    const applied = SessionDocument.applySavedLayout(fresh, layout);
    assert.equal(applied.ok, true);
    assert.equal(applied.session.pieces["instance:a"].mirrored, true);
    assert.equal(applied.session.pieces["instance:a"].flip_h, true);

    const legacyLayout = {
        schema: 1,
        pieces: [{
            piece_instance_id: "pi-a",
            sheet_no: 1,
            local_x_mm: 10,
            local_y_mm: 20,
            rotation_deg: 0,
            distribution: "active",
            exclusion_reason: null,
            glass_host_piece_id: null,
        }],
        boards: [{ sheet_no: 1, origin_x_mm: 0, origin_y_mm: 0, user_moved: false }],
    };
    const legacy = SessionDocument.applySavedLayout(
        sessionFor(rectPiece({ piece_type: "L-Shaped Corner" })),
        legacyLayout
    );
    assert.equal(legacy.ok, true);
    assert.equal(legacy.session.pieces["instance:a"].mirrored, false);
    assert.equal(legacy.session.pieces["instance:a"].flip_h, false);
}

// Page-action contract and transform controls remain in the renderer source.
{
    const canvas = fs.readFileSync(path.join(root, "public/js/board_editor/canvas_renderer.js"), "utf8");
    const controller = fs.readFileSync(path.join(root, "public/js/board_editor/controller.js"), "utf8");
    const css = fs.readFileSync(path.join(root, "public/css/board_editor.css"), "utf8");
    const page = fs.readFileSync(path.join(root, "almdina_erp/page/board_editor/board_editor.js"), "utf8");
    const arCsv = fs.readFileSync(path.join(root, "translations/ar.csv"), "utf8");
    assert.match(canvas, /renderPageActions/);
    assert.match(canvas, /abe-page-actions/);
    assert.match(canvas, /abe-angle-0-180/);
    assert.match(canvas, /abe-angle-90-270/);
    assert.match(canvas, /arrow-left-right/);
    assert.match(canvas, /arrow-up-down/);
    assert.match(canvas, /abe-rotate-30/);
    assert.match(canvas, /abe-angle-mirror/);
    assert.match(canvas, /flip-horizontal-2/);
    assert.match(canvas, /Toggle rotation 0° ↔ 180°/);
    assert.match(canvas, /Toggle rotation 90° ↔ 270°/);
    assert.doesNotMatch(canvas, /abe-float-tools[\s\S]*abe-create-plan/);
    assert.doesNotMatch(canvas, /abe-flip-h/);
    assert.doesNotMatch(canvas, /anglePairIcon/);
    assert.match(controller, /ensurePageActionsHost/);
    assert.match(controller, /paintPageActions/);
    assert.match(controller, /toggleAngle0_180/);
    assert.match(controller, /toggleAngle90_270/);
    assert.match(controller, /applyNumericAngle/);
    assert.match(controller, /rememberApplyReturnContext/);
    assert.match(css, /abe-page-actions/);
    assert.match(css, /padding-inline-end:\s*12px/);
    assert.match(css, /max-width:\s*none/);
    assert.match(css, /margin-inline-start:\s*auto/);
    assert.match(css, /\.abe-page-actions[\s\S]*border:\s*0/);
    assert.match(css, /\.abe-page-actions \.abe-tool-btn[\s\S]*border:\s*0/);
    assert.match(page, /transform_geometry\.js\?v=2/);
    assert.match(page, /position_geometry\.js\?v=4/);
    assert.match(page, /controller\.js\?v=33/);
    assert.match(page, /canvas_renderer\.js\?v=36/);
    assert.match(page, /board_editor\.css\?v=36/);
    assert.match(page, /move_geometry\.js\?v=20/);
    assert.match(canvas, /data-abe-angle-mirror/);
    assert.match(canvas, /abe-l-mirror-btn/);
    assert.match(arCsv, /Toggle rotation 0° ↔ 180°/);
    assert.match(arCsv, /Toggle rotation 90° ↔ 270°/);
}

console.log("board_editor_transform.test.js: ok");
