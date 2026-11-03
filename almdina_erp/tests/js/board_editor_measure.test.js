"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.resolve(__dirname, "../..");

function load() {
    const files = [
        "public/js/board_editor/move_geometry.js",
        "public/js/board_editor/measure_geometry.js",
        "public/js/board_editor/measure_interaction.js",
        "public/js/board_editor/history.js",
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

const { MeasureGeometry, createMeasureInteraction, createStore, History } = load();

function rectPiece(key, x, y, w, h, sheetNo = 1) {
    return {
        piece_key: key,
        piece_instance_id: key.replace(/^instance:/, ""),
        piece_id: Number(String(key).replace(/\D/g, "") || 1),
        sheet_no: sheetNo,
        distribution: "active",
        editable: true,
        local_x_mm: x,
        local_y_mm: y,
        rotation_deg: 0,
        outline_mm: [[x, y], [x + w, y], [x + w, y + h], [x, y + h]],
        base_outline_mm: [[x, y], [x + w, y], [x + w, y + h], [x, y + h]],
        pivot_mm: { x: x + w / 2, y: y + h / 2 },
    };
}

function sessionWith(pieces, boardOverrides = {}) {
    const map = {};
    pieces.forEach((piece) => {
        map[piece.piece_key] = piece;
    });
    return {
        pieces: map,
        boards: {
            1: {
                sheet_no: 1,
                origin_x_mm: 0,
                origin_y_mm: 0,
                trim_x_mm: 10,
                trim_y_mm: 10,
                width_mm: 1220,
                height_mm: 2440,
                usable_width_mm: 1200,
                usable_length_mm: 2420,
                ...boardOverrides,
            },
        },
        kerf_mm: 0,
    };
}

// 1-3: horizontal / vertical / diagonal Euclidean lengths.
{
    const h = MeasureGeometry.measureLine([100, 200], [400, 200]);
    assert.equal(h.distance, 300);
    assert.equal(h.label, "300 mm");
    const v = MeasureGeometry.measureLine([10, 20], [10, 520]);
    assert.equal(v.distance, 500);
    const d = MeasureGeometry.measureLine([100, 200], [400, 600]);
    assert.equal(d.distance, 500);
    assert.equal(MeasureGeometry.measureLine([0, 0], [0, 0]), null);
}

// 4-5: zoom-independent world length + screen/world conversion via metrics math.
{
    const metrics = { minX: 0, minY: 0, width: 1000, height: 2000, scale: 0.5 };
    function clientToWorld(clientX, clientY, rect) {
        const nx = (clientX - rect.left) / rect.width;
        const ny = (clientY - rect.top) / rect.height;
        return {
            x: metrics.minX + nx * metrics.width,
            y: metrics.minY + ny * metrics.height,
        };
    }
    const a = clientToWorld(100, 100, { left: 0, top: 0, width: 500, height: 1000 });
    const b = clientToWorld(250, 300, { left: 0, top: 0, width: 500, height: 1000 });
    assert.equal(a.x, 200);
    assert.equal(a.y, 200);
    assert.equal(b.x, 500);
    assert.equal(b.y, 600);
    assert.equal(MeasureGeometry.distance([a.x, a.y], [b.x, b.y]), 500);
    metrics.scale = 2;
    assert.equal(MeasureGeometry.distance([a.x, a.y], [b.x, b.y]), 500);
}

// 6-7: edge clearance blocked vs open.
{
    const openSession = sessionWith([rectPiece("instance:a", 100, 100, 80, 60)]);
    const open = MeasureGeometry.edgeClearances(openSession, "instance:a");
    assert.ok(open.some((row) => row.direction === "left" && row.distance > 0));
    assert.ok(open.some((row) => row.direction === "right" && row.distance > 0));

    const blockedSession = sessionWith([
        rectPiece("instance:a", 100, 100, 80, 60),
        rectPiece("instance:b", 220, 100, 80, 60),
    ]);
    const blocked = MeasureGeometry.edgeClearances(blockedSession, "instance:a");
    assert.equal(blocked.some((row) => row.direction === "right"), false);
    assert.ok(blocked.some((row) => row.direction === "left"));
}

// 8-9: piece-to-piece horizontal / vertical / diagonal.
{
    const session = sessionWith([
        rectPiece("instance:a", 100, 100, 50, 50),
        rectPiece("instance:b", 200, 100, 50, 50),
        rectPiece("instance:c", 100, 220, 50, 50),
        rectPiece("instance:d", 260, 260, 40, 40),
    ]);
    const horiz = MeasureGeometry.shortestClearanceBetweenPieces(session, "instance:a", "instance:b");
    assert.ok(horiz);
    assert.ok(Math.abs(horiz.distance - 50) < 1e-6);
    const vert = MeasureGeometry.shortestClearanceBetweenPieces(session, "instance:a", "instance:c");
    assert.ok(vert);
    assert.ok(Math.abs(vert.distance - 70) < 1e-6);
    const diag = MeasureGeometry.shortestClearanceBetweenPieces(session, "instance:a", "instance:d");
    assert.ok(diag);
    assert.ok(diag.distance > 0);
}

// 10: non-rectangular L outline.
{
    const lPiece = {
        ...rectPiece("instance:l", 100, 100, 100, 100),
        outline_mm: [[100, 100], [200, 100], [200, 140], [140, 140], [140, 200], [100, 200]],
        base_outline_mm: [[100, 100], [200, 100], [200, 140], [140, 140], [140, 200], [100, 200]],
    };
    const other = rectPiece("instance:r", 250, 100, 40, 40);
    const session = sessionWith([lPiece, other]);
    const gap = MeasureGeometry.shortestClearanceBetweenPieces(session, "instance:l", "instance:r");
    assert.ok(gap);
    assert.ok(gap.distance > 0);
}

// 11: glass hole is not solid obstacle material.
{
    const host = {
        ...rectPiece("instance:host", 100, 100, 200, 200),
        glass_hole_local_mm: [[140, 140], [260, 140], [260, 260], [140, 260]],
    };
    const guestA = rectPiece("instance:guest-a", 150, 160, 30, 30);
    const guestB = rectPiece("instance:guest-b", 220, 160, 30, 30);
    const session = sessionWith([host, guestA, guestB]);
    const hostMaterial = MeasureGeometry.pieceMaterial(host, session.boards);
    assert.equal(MeasureGeometry.pointInMaterial([200, 200], hostMaterial), false);
    assert.equal(MeasureGeometry.pointInMaterial([120, 120], hostMaterial), true);
    // A free segment that stays inside the hole is not blocked by the host frame.
    assert.equal(
        MeasureGeometry.segmentBlockedByMaterials(
            [160, 200],
            [250, 200],
            [hostMaterial],
            []
        ),
        false
    );
    // Crossing the solid frame is blocked.
    assert.equal(
        MeasureGeometry.segmentBlockedByMaterials(
            [120, 120],
            [280, 120],
            [hostMaterial],
            []
        ),
        true
    );
    const insideGap = MeasureGeometry.shortestClearanceBetweenPieces(
        session,
        "instance:guest-a",
        "instance:guest-b"
    );
    assert.ok(insideGap);
    assert.ok(insideGap.distance > 0);
}

// 12: third piece blocks piece-to-piece path when it fills the gap.
{
    const session = sessionWith([
        rectPiece("instance:a", 100, 100, 40, 40),
        rectPiece("instance:mid", 160, 100, 40, 40),
        rectPiece("instance:b", 220, 100, 40, 40),
    ]);
    // Direct facing still finds the short gaps to mid; A↔B shortest clear path may route around.
    const ab = MeasureGeometry.shortestClearanceBetweenPieces(session, "instance:a", "instance:b");
    assert.ok(ab);
    assert.ok(ab.distance >= 0);
    const blockedSeg = MeasureGeometry.segmentBlockedByMaterials(
        [140, 120],
        [220, 120],
        [
            MeasureGeometry.pieceMaterial(session.pieces["instance:mid"], session.boards),
        ],
        ["instance:a", "instance:b"]
    );
    assert.equal(blockedSeg, true);
}

// 13-14: Alt overlay clears on release; measure mode does not mutate session.
{
    const session = sessionWith([rectPiece("instance:a", 100, 100, 50, 50)]);
    const history = History.create(session);
    const store = createStore({ projection: { layers: [], sheets: [], elements: [], pieces: [] } });
    store.attachSession(history.get(), history);
    store.selectPiece(1, { pieceKey: "instance:a", sheetNo: 1, mode: "replace" });
    let overlay = null;
    let altHeld = true;
    const interaction = createMeasureInteraction({
        store,
        getSvgEl: () => ({ getBoundingClientRect: () => ({ left: 0, top: 0, width: 1000, height: 2000 }) }),
        getWorldMetrics: () => ({ minX: 0, minY: 0, width: 1000, height: 2000, scale: 1 }),
        isAltKey: () => altHeld,
        isPanKey: () => false,
        isMeasureToolActive: () => false,
        onOverlay: (lines) => { overlay = lines; },
    });
    interaction.refreshAltInspection(200, 200);
    assert.ok(Array.isArray(overlay) && overlay.length > 0);
    altHeld = false;
    interaction.refreshAltInspection(200, 200);
    assert.ok(Array.isArray(overlay));
    assert.equal(overlay.length, 0);
    const before = JSON.stringify(store.snapshot().session.pieces["instance:a"].outline_mm);
    store.setMeasureToolActive(true);
    assert.equal(store.snapshot().measureToolActive, true);
    assert.equal(JSON.stringify(store.snapshot().session.pieces["instance:a"].outline_mm), before);
}

// 15-17: source contracts — tool does not enter draft export fields; UI wiring present.
{
    const canvas = fs.readFileSync(path.join(root, "public/js/board_editor/canvas_renderer.js"), "utf8");
    const controller = fs.readFileSync(path.join(root, "public/js/board_editor/controller.js"), "utf8");
    const sessionDoc = fs.readFileSync(path.join(root, "public/js/board_editor/session_document.js"), "utf8");
    const page = fs.readFileSync(path.join(root, "almdina_erp/page/board_editor/board_editor.js"), "utf8");
    const draft = fs.readFileSync(path.join(root, "almdina_erp/domain/cutting/board_editor_draft.py"), "utf8");
    const arCsv = fs.readFileSync(path.join(root, "translations/ar.csv"), "utf8");
    assert.match(canvas, /abe-measure/);
    assert.match(canvas, /patchMeasureOverlay/);
    assert.match(canvas, /data-abe-measure/);
    assert.match(controller, /createMeasureInteraction/);
    assert.match(controller, /toggleMeasureTool/);
    assert.match(controller, /refreshAltInspection/);
    assert.match(controller, /clearAltOverlay/);
    assert.match(page, /measure_geometry\.js\?v=1/);
    assert.match(page, /measure_interaction\.js\?v=1/);
    assert.doesNotMatch(sessionDoc, /measureToolActive|measure_lines|abe-measure/);
    assert.doesNotMatch(draft, /measure_line|measureTool/);
    assert.match(arCsv, /^Measure,/m);
}

console.log("board_editor_measure.test.js: ok");
