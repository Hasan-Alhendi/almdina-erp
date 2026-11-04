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

const BoardEditor = load();
const {
    MeasureGeometry,
    createMeasureInteraction,
    createStore,
    History,
} = BoardEditor;

function aabbGap(boundsA, boundsB) {
    const ax1 = boundsA.x + boundsA.w;
    const ay1 = boundsA.y + boundsA.h;
    const bx1 = boundsB.x + boundsB.w;
    const by1 = boundsB.y + boundsB.h;
    const gapX = Math.max(0, Math.max(boundsA.x - bx1, boundsB.x - ax1));
    const gapY = Math.max(0, Math.max(boundsA.y - by1, boundsB.y - ay1));
    if (gapX > 0 && gapY === 0) {
        const y = Math.min(ay1, by1) - Math.max(boundsA.y, boundsB.y);
        const midY = Math.max(boundsA.y, boundsB.y) + Math.max(y, 0) / 2;
        if (ax1 <= boundsB.x) {
            return {
                kind: "piece",
                start: [ax1, midY],
                end: [boundsB.x, midY],
                distance: gapX,
            };
        }
        return {
            kind: "piece",
            start: [bx1, midY],
            end: [boundsA.x, midY],
            distance: gapX,
        };
    }
    if (gapY > 0 && gapX === 0) {
        const x = Math.min(ax1, bx1) - Math.max(boundsA.x, boundsB.x);
        const midX = Math.max(boundsA.x, boundsB.x) + Math.max(x, 0) / 2;
        if (ay1 <= boundsB.y) {
            return {
                kind: "piece",
                start: [midX, ay1],
                end: [midX, boundsB.y],
                distance: gapY,
            };
        }
        return {
            kind: "piece",
            start: [midX, by1],
            end: [midX, boundsA.y],
            distance: gapY,
        };
    }
    const distance = Math.hypot(gapX, gapY);
    return {
        kind: "piece",
        start: [boundsA.x + boundsA.w / 2, boundsA.y + boundsA.h / 2],
        end: [boundsB.x + boundsB.w / 2, boundsB.y + boundsB.h / 2],
        distance,
    };
}

function installFastClearanceGeometry() {
    const real = BoardEditor.MeasureGeometry;
    BoardEditor.MeasureGeometry = Object.freeze({
        ...real,
        edgeClearances(session, pieceKey) {
            const piece = session.pieces[pieceKey];
            const board = session.boards[String(piece.sheet_no)];
            const outer = real.boardOuterWorld(board);
            const material = real.pieceMaterial(piece, session.boards);
            if (!outer || !material) return [];
            const b = material.bounds;
            return [
                {
                    kind: "edge",
                    direction: "left",
                    start: [b.x, b.y + b.h / 2],
                    end: [outer.x, b.y + b.h / 2],
                    distance: b.x - outer.x,
                },
                {
                    kind: "edge",
                    direction: "right",
                    start: [b.x + b.w, b.y + b.h / 2],
                    end: [outer.right, b.y + b.h / 2],
                    distance: outer.right - (b.x + b.w),
                },
                {
                    kind: "edge",
                    direction: "top",
                    start: [b.x + b.w / 2, b.y],
                    end: [b.x + b.w / 2, outer.y],
                    distance: b.y - outer.y,
                },
                {
                    kind: "edge",
                    direction: "bottom",
                    start: [b.x + b.w / 2, b.y + b.h],
                    end: [b.x + b.w / 2, outer.bottom],
                    distance: outer.bottom - (b.y + b.h),
                },
            ].filter((row) => row.distance >= 0);
        },
        shortestClearanceBetweenPieces(session, pieceKeyA, pieceKeyB) {
            const pieceA = session.pieces[pieceKeyA];
            const pieceB = session.pieces[pieceKeyB];
            if (!pieceA || !pieceB) return null;
            const matA = real.pieceMaterial(pieceA, session.boards);
            const matB = real.pieceMaterial(pieceB, session.boards);
            if (!matA || !matB) return null;
            const gap = aabbGap(matA.bounds, matB.bounds);
            return {
                ...gap,
                pieceKeyA,
                pieceKeyB,
            };
        },
    });
    return () => {
        BoardEditor.MeasureGeometry = real;
    };
}

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

// 4-5: zoom-independent world length + padded SVG client→world conversion.
{
    const history = History.create(sessionWith([]));
    const store = createStore({ projection: { layers: [], sheets: [], elements: [], pieces: [] } });
    store.attachSession(history.get(), history);
    const pad = 16;
    const scale = 0.5;
    const metrics = {
        minX: 0,
        minY: 0,
        width: 1000,
        height: 2000,
        scale,
        pad,
        contentWidth: 1000 * scale + pad * 2,
        contentHeight: 2000 * scale + pad * 2 + 72,
    };
    const svg = {
        getAttribute: (name) => (name === "width"
            ? String(metrics.contentWidth)
            : name === "height" ? String(metrics.contentHeight) : null),
        getBoundingClientRect: () => ({
            left: 0,
            top: 0,
            width: metrics.contentWidth,
            height: metrics.contentHeight,
        }),
    };
    const interaction = createMeasureInteraction({
        store,
        getSvgEl: () => svg,
        getWorldMetrics: () => metrics,
        isAltKey: () => false,
        isPanKey: () => false,
        isMeasureToolActive: () => false,
        onOverlay: () => {},
    });
    // World (0,0) sits at SVG user (pad, pad) after the .abe-world transform.
    const origin = interaction.clientToWorld(pad, pad);
    assert.ok(origin);
    assert.ok(Math.abs(origin.x) < 1e-9);
    assert.ok(Math.abs(origin.y) < 1e-9);
    const a = interaction.clientToWorld(pad + 200 * scale, pad + 200 * scale);
    const b = interaction.clientToWorld(pad + 500 * scale, pad + 600 * scale);
    assert.ok(Math.abs(a.x - 200) < 1e-9);
    assert.ok(Math.abs(a.y - 200) < 1e-9);
    assert.ok(Math.abs(b.x - 500) < 1e-9);
    assert.ok(Math.abs(b.y - 600) < 1e-9);
    assert.equal(MeasureGeometry.distance([a.x, a.y], [b.x, b.y]), 500);
    // Naive full-rect mapping (legacy) is wrong once pad/float clearance exist.
    const naiveX = ((pad + 200 * scale) / metrics.contentWidth) * metrics.width;
    assert.notEqual(Math.round(naiveX), 200);
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
    assert.match(page, /measure_interaction\.js\?v=2/);
    assert.doesNotMatch(sessionDoc, /measureToolActive|measure_lines|abe-measure/);
    assert.doesNotMatch(draft, /measure_line|measureTool/);
    assert.match(arCsv, /^Measure,/m);
}

function makeAltHarness(pieces) {
    const restoreGeometry = installFastClearanceGeometry();
    const session = sessionWith(pieces);
    const history = History.create(session);
    const store = createStore({ projection: { layers: [], sheets: [], elements: [], pieces: [] } });
    store.attachSession(history.get(), history);
    let overlay = null;
    let altHeld = true;
    const scale = 1;
    const pad = 16;
    const metrics = {
        minX: 0,
        minY: 0,
        width: 1220,
        height: 2440,
        scale,
        pad,
        contentWidth: 1220 * scale + pad * 2,
        contentHeight: 2440 * scale + pad * 2 + 72,
    };
    const svg = {
        getAttribute: (name) => (name === "width"
            ? String(metrics.contentWidth)
            : name === "height" ? String(metrics.contentHeight) : null),
        getBoundingClientRect: () => ({
            left: 0,
            top: 0,
            width: metrics.contentWidth,
            height: metrics.contentHeight,
        }),
    };
    const interaction = createMeasureInteraction({
        store,
        getSvgEl: () => svg,
        getWorldMetrics: () => metrics,
        isAltKey: () => altHeld,
        isPanKey: () => false,
        isMeasureToolActive: () => false,
        onOverlay: (lines) => { overlay = lines; },
    });
    function toClient(worldX, worldY) {
        return {
            x: pad + worldX * scale,
            y: pad + worldY * scale,
        };
    }
    function moveTo(worldX, worldY, eventExtras = {}) {
        const client = toClient(worldX, worldY);
        interaction.onPointerMove({
            clientX: client.x,
            clientY: client.y,
            altKey: altHeld,
            ...eventExtras,
        });
        return overlay;
    }
    return {
        store,
        history,
        interaction,
        moveTo,
        setAlt(value) { altHeld = Boolean(value); },
        getOverlay: () => overlay,
        metrics,
        toClient,
        dispose: restoreGeometry,
    };
}

function overlayMode(overlay) {
    if (!Array.isArray(overlay) || !overlay.length) return "none";
    if (overlay.some((row) => row && (row.kind === "edge" || row.direction))) return "edge";
    return "piece";
}

// 18: Alt hover transitions Empty → B → Empty → C → B → Empty without reselection.
{
    const harness = makeAltHarness([
        rectPiece("instance:a", 100, 100, 50, 50),
        rectPiece("instance:b", 300, 100, 50, 50),
        rectPiece("instance:c", 100, 300, 50, 50),
    ]);
    harness.store.selectPiece(1, { pieceKey: "instance:a", sheetNo: 1, mode: "replace" });
    const sequence = [
        { point: [40, 40], expect: "edge" },
        { point: [325, 125], expect: "piece", other: "instance:b", distance: 150 },
        { point: [40, 40], expect: "edge" },
        { point: [125, 325], expect: "piece", other: "instance:c", distance: 150 },
        { point: [325, 125], expect: "piece", other: "instance:b", distance: 150 },
        { point: [40, 40], expect: "edge" },
    ];
    sequence.forEach((step, index) => {
        const overlay = harness.moveTo(step.point[0], step.point[1]);
        assert.equal(
            overlayMode(overlay),
            step.expect,
            `step ${index} expected ${step.expect}`
        );
        assert.ok(overlay.length > 0, `step ${index} must publish lines`);
        if (step.other) {
            assert.equal(overlay[0].pieceKeyB, step.other, `step ${index} target`);
            assert.ok(Math.abs(overlay[0].distance - step.distance) < 1e-6);
        }
        assert.equal(harness.store.snapshot().selectedPieceKey, "instance:a");
    });
    harness.dispose();
}

// 19: CTM inverse path preferred when available (zoom/scroll/transform safe).
{
    const harness = makeAltHarness([rectPiece("instance:a", 100, 100, 50, 50)]);
    const scale = 2;
    const pad = 16;
    const worldGroup = {
        getScreenCTM: () => ({
            a: scale, b: 0, c: 0, d: scale, e: pad, f: pad,
            inverse() {
                const det = scale * scale;
                return {
                    a: scale / det,
                    b: 0,
                    c: 0,
                    d: scale / det,
                    e: -pad / scale,
                    f: -pad / scale,
                };
            },
        }),
    };
    const svg = {
        querySelector: (sel) => (sel === ".abe-world" ? worldGroup : null),
        getBoundingClientRect: () => ({ left: 10, top: 20, width: 400, height: 800 }),
        getAttribute: () => null,
    };
    const interaction = createMeasureInteraction({
        store: harness.store,
        getSvgEl: () => svg,
        getWorldMetrics: () => ({ minX: 0, minY: 0, width: 1000, height: 2000, scale: 0.1, pad: 99 }),
        isAltKey: () => false,
        isPanKey: () => false,
        isMeasureToolActive: () => false,
        onOverlay: () => {},
    });
    // Screen (pad + 120*scale, pad + 80*scale) → world (120, 80) via CTM, ignoring stale metrics.
    const world = interaction.clientToWorld(pad + 120 * scale, pad + 80 * scale);
    assert.ok(world);
    assert.ok(Math.abs(world.x - 120) < 1e-9);
    assert.ok(Math.abs(world.y - 80) < 1e-9);
    harness.dispose();
}

// 20: geometry cache skips repeats over same target; recomputes on hover change / geometry edit.
{
    const harness = makeAltHarness([
        rectPiece("instance:a", 100, 100, 50, 50),
        rectPiece("instance:b", 300, 100, 50, 50),
    ]);
    harness.store.selectPiece(1, { pieceKey: "instance:a", sheetNo: 1, mode: "replace" });
    harness.interaction.resetGeometryComputeCount();
    harness.moveTo(40, 40);
    harness.moveTo(42, 41);
    harness.moveTo(45, 44);
    const edgeComputes = harness.interaction.getGeometryComputeCount();
    assert.equal(edgeComputes, 1, "empty hover must compute once while target stays empty");
    harness.moveTo(325, 125);
    assert.equal(harness.interaction.getGeometryComputeCount(), 2);
    harness.moveTo(330, 128);
    harness.moveTo(320, 122);
    assert.equal(
        harness.interaction.getGeometryComputeCount(),
        2,
        "same piece hover must not recompute clearance"
    );
    const moved = JSON.parse(JSON.stringify(harness.store.snapshot().session));
    moved.pieces["instance:b"].local_x_mm = 340;
    moved.pieces["instance:b"].outline_mm = [[340, 100], [390, 100], [390, 150], [340, 150]];
    moved.pieces["instance:b"].base_outline_mm = moved.pieces["instance:b"].outline_mm;
    harness.history.commit(moved);
    harness.store.attachSession(harness.history.get(), harness.history);
    harness.store.selectPiece(1, { pieceKey: "instance:a", sheetNo: 1, mode: "replace" });
    const before = harness.interaction.getGeometryComputeCount();
    const overlayAfterMove = harness.moveTo(360, 125);
    assert.equal(harness.interaction.getGeometryComputeCount(), before + 1);
    assert.equal(overlayMode(overlayAfterMove), "piece");
    assert.ok(Math.abs(overlayAfterMove[0].distance - 190) < 1e-6);
    harness.dispose();
}

// 21: clear selection and Alt release drop stale overlay; Alt re-press restores.
{
    const harness = makeAltHarness([
        rectPiece("instance:a", 100, 100, 50, 50),
        rectPiece("instance:b", 300, 100, 50, 50),
    ]);
    harness.store.selectPiece(1, { pieceKey: "instance:a", sheetNo: 1, mode: "replace" });
    assert.equal(overlayMode(harness.moveTo(325, 125)), "piece");
    harness.store.selectPiece(null, { mode: "replace" });
    harness.moveTo(325, 125);
    assert.equal(overlayMode(harness.getOverlay()), "none");

    harness.store.selectPiece(1, { pieceKey: "instance:a", sheetNo: 1, mode: "replace" });
    assert.equal(overlayMode(harness.moveTo(325, 125)), "piece");
    harness.setAlt(false);
    harness.interaction.onPointerMove({
        clientX: harness.toClient(325, 125).x,
        clientY: harness.toClient(325, 125).y,
        altKey: false,
    });
    assert.equal(overlayMode(harness.getOverlay()), "none");
    harness.setAlt(true);
    harness.interaction.onPointerMove({
        clientX: harness.toClient(325, 125).x,
        clientY: harness.toClient(325, 125).y,
        altKey: true,
    });
    assert.equal(overlayMode(harness.getOverlay()), "piece");
    harness.dispose();
}

// 22: multi-select keeps Alt overlay suppressed.
{
    const harness = makeAltHarness([
        rectPiece("instance:a", 100, 100, 50, 50),
        rectPiece("instance:b", 300, 100, 50, 50),
    ]);
    harness.store.selectPiece(1, { pieceKey: "instance:a", sheetNo: 1, mode: "replace" });
    harness.store.selectPiece(1, { pieceKey: "instance:b", sheetNo: 1, mode: "toggle" });
    assert.ok(harness.store.snapshot().selectedPieceKeys.length > 1);
    harness.moveTo(40, 40);
    assert.equal(overlayMode(harness.getOverlay()), "none");
    harness.dispose();
}

// 23: hovering the selected piece itself uses edge clearances (not self-gap).
{
    const harness = makeAltHarness([
        rectPiece("instance:a", 100, 100, 50, 50),
        rectPiece("instance:b", 300, 100, 50, 50),
    ]);
    harness.store.selectPiece(1, { pieceKey: "instance:a", sheetNo: 1, mode: "replace" });
    assert.equal(overlayMode(harness.moveTo(125, 125)), "edge");
    harness.dispose();
}

// 24: third-piece blocking still comes from real geometry (not the fast harness stub).
{
    const session = sessionWith([
        rectPiece("instance:a", 100, 100, 40, 40),
        rectPiece("instance:mid", 160, 100, 40, 40),
        rectPiece("instance:b", 220, 100, 40, 40),
    ]);
    assert.equal(
        MeasureGeometry.segmentBlockedByMaterials(
            [140, 120],
            [220, 120],
            [MeasureGeometry.pieceMaterial(session.pieces["instance:mid"], session.boards)],
            ["instance:a", "instance:b"]
        ),
        true
    );
}

console.log("board_editor_measure.test.js: ok");
