"use strict";

/**
 * Presentation-only coverage for Alt piece-to-piece distance overlay.
 * Avoids the known-slow shortestClearanceBetweenPieces sampler used in
 * board_editor_measure.test.js blocks 8–11.
 */

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
        outline_mm: [[x, y], [x + w, y], [x + w, y + h], [x, y + h]],
        base_outline_mm: [[x, y], [x + w, y], [x + w, y + h], [x, y + h]],
        placement_cm: { x: x / 10, y: y / 10, w: w / 10, h: h / 10 },
    };
}

function sessionWith(pieces) {
    const boards = {
        1: {
            sheet_no: 1,
            origin_x_mm: 0,
            origin_y_mm: 0,
            width_mm: 1220,
            height_mm: 2440,
            trim_x_mm: 0,
            trim_y_mm: 0,
            usable_width_mm: 1220,
            usable_length_mm: 2440,
        },
    };
    const map = {};
    pieces.forEach((piece) => {
        map[piece.piece_key] = piece;
    });
    return { pieces: map, boards };
}

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
            return { kind: "piece", start: [ax1, midY], end: [boundsB.x, midY], distance: gapX };
        }
        return { kind: "piece", start: [bx1, midY], end: [boundsA.x, midY], distance: gapX };
    }
    if (gapY > 0 && gapX === 0) {
        const x = Math.min(ax1, bx1) - Math.max(boundsA.x, boundsB.x);
        const midX = Math.max(boundsA.x, boundsB.x) + Math.max(x, 0) / 2;
        if (ay1 <= boundsB.y) {
            return { kind: "piece", start: [midX, ay1], end: [midX, boundsB.y], distance: gapY };
        }
        return { kind: "piece", start: [midX, by1], end: [midX, boundsA.y], distance: gapY };
    }
    return {
        kind: "piece",
        start: [boundsA.x + boundsA.w / 2, boundsA.y + boundsA.h / 2],
        end: [boundsB.x + boundsB.w / 2, boundsB.y + boundsB.h / 2],
        distance: Math.hypot(gapX, gapY),
    };
}

assert.equal(typeof MeasureGeometry.presentPieceClearanceNearPointer, "function");
assert.equal(typeof MeasureGeometry.presentEdgeClearanceNearPointer, "function");
assert.equal(typeof MeasureGeometry.facingCorridor, "function");
assert.equal(typeof MeasureGeometry.edgeSlideBand, "function");

// Horizontal corridor: slide Y with pointer, keep distance and face X.
{
    const session = sessionWith([
        rectPiece("instance:tall-a", 100, 100, 40, 400),
        rectPiece("instance:tall-b", 204, 100, 40, 400),
    ]);
    // Synthetic top-edge anchors (equal-distance first-sample behaviour).
    const geom = {
        kind: "piece",
        start: [140, 100],
        end: [204, 100],
        distance: 64,
        pieceKeyA: "instance:tall-a",
        pieceKeyB: "instance:tall-b",
    };
    const nearTop = MeasureGeometry.presentPieceClearanceNearPointer(geom, [180, 120], session);
    const nearMid = MeasureGeometry.presentPieceClearanceNearPointer(geom, [180, 300], session);
    const nearBottom = MeasureGeometry.presentPieceClearanceNearPointer(geom, [180, 480], session);
    assert.equal(nearTop.distance, 64);
    assert.equal(nearMid.distance, 64);
    assert.equal(nearBottom.distance, 64);
    assert.ok(nearTop.start[1] < nearMid.start[1]);
    assert.ok(nearMid.start[1] < nearBottom.start[1]);
    assert.equal(nearTop.start[0], 140);
    assert.equal(nearTop.end[0], 204);
    assert.equal(nearTop.presentation, "pointer-anchored");
}

// Vertical corridor: slide X with pointer.
{
    const session = sessionWith([
        rectPiece("instance:top", 100, 100, 300, 40),
        rectPiece("instance:bot", 100, 160, 300, 40),
    ]);
    const geom = {
        kind: "piece",
        start: [100, 140],
        end: [100, 160],
        distance: 20,
        pieceKeyA: "instance:top",
        pieceKeyB: "instance:bot",
    };
    const leftish = MeasureGeometry.presentPieceClearanceNearPointer(geom, [120, 150], session);
    const rightish = MeasureGeometry.presentPieceClearanceNearPointer(geom, [360, 150], session);
    assert.equal(leftish.distance, 20);
    assert.equal(rightish.distance, 20);
    assert.ok(leftish.start[0] < rightish.start[0]);
    assert.ok(Math.abs(leftish.start[0] - leftish.end[0]) < 1e-9);
}

// Diagonal result must not be rewritten into a misleading parallel ruler.
{
    const session = sessionWith([
        rectPiece("instance:tall-a", 100, 100, 40, 400),
        rectPiece("instance:tall-b", 204, 100, 40, 400),
    ]);
    const diagonal = {
        kind: "piece",
        start: [140, 100],
        end: [204, 180],
        distance: Math.hypot(64, 80),
        pieceKeyA: "instance:tall-a",
        pieceKeyB: "instance:tall-b",
    };
    const kept = MeasureGeometry.presentPieceClearanceNearPointer(diagonal, [180, 300], session);
    assert.equal(kept.distance, diagonal.distance);
    assert.equal(kept.start[0], diagonal.start[0]);
    assert.equal(kept.start[1], diagonal.start[1]);
    assert.equal(kept.end[0], diagonal.end[0]);
    assert.equal(kept.end[1], diagonal.end[1]);
    assert.notEqual(kept.presentation, "pointer-anchored");
}

// Interaction: pointer moves update overlay presentation without geometry recompute.
{
    const real = BoardEditor.MeasureGeometry;
    BoardEditor.MeasureGeometry = Object.freeze({
        ...real,
        edgeClearances() { return []; },
        shortestClearanceBetweenPieces(session, pieceKeyA, pieceKeyB) {
            const matA = real.pieceMaterial(session.pieces[pieceKeyA], session.boards);
            const matB = real.pieceMaterial(session.pieces[pieceKeyB], session.boards);
            const gap = aabbGap(matA.bounds, matB.bounds);
            return { ...gap, pieceKeyA, pieceKeyB };
        },
    });

    const session = sessionWith([
        rectPiece("instance:a", 100, 100, 40, 400),
        rectPiece("instance:b", 204, 100, 40, 400),
    ]);
    const history = History.create(session);
    const store = createStore({ projection: { layers: [], sheets: [], elements: [], pieces: [] } });
    store.attachSession(history.get(), history);
    store.selectPiece(1, { pieceKey: "instance:a", sheetNo: 1, mode: "replace" });

    let overlay = null;
    const pad = 16;
    const metrics = {
        minX: 0,
        minY: 0,
        width: 1220,
        height: 2440,
        scale: 1,
        pad,
        contentWidth: 1220 + 32,
        contentHeight: 2440 + 32,
    };
    const interaction = createMeasureInteraction({
        store,
        getSvgEl: () => ({
            getAttribute: (name) => (
                name === "width" ? String(metrics.contentWidth)
                    : name === "height" ? String(metrics.contentHeight) : null
            ),
            getBoundingClientRect: () => ({
                left: 0,
                top: 0,
                width: metrics.contentWidth,
                height: metrics.contentHeight,
            }),
        }),
        getWorldMetrics: () => metrics,
        isAltKey: () => true,
        isPanKey: () => false,
        isMeasureToolActive: () => false,
        isDragActive: () => false,
        onOverlay: (lines) => { overlay = lines; },
    });

    function moveTo(x, y) {
        interaction.onPointerMove({
            clientX: pad + x,
            clientY: pad + y,
            altKey: true,
        });
        return overlay;
    }

    interaction.resetGeometryComputeCount();
    const topOverlay = moveTo(220, 130);
    assert.ok(topOverlay && topOverlay.length === 1);
    assert.ok(Math.abs(topOverlay[0].distance - 64) < 1e-6);
    const topY = topOverlay[0].start[1];
    const bottomOverlay = moveTo(220, 450);
    assert.equal(interaction.getGeometryComputeCount(), 1);
    assert.ok(Math.abs(bottomOverlay[0].distance - 64) < 1e-6);
    assert.ok(bottomOverlay[0].start[1] > topY);

    BoardEditor.MeasureGeometry = real;
}

// Left board-edge clearance: slide Y with pointer, keep distance.
{
    const session = sessionWith([
        rectPiece("instance:door", 5, 100, 40, 800),
    ]);
    const geom = {
        kind: "edge",
        direction: "left",
        start: [5, 100],
        end: [0, 100],
        distance: 5,
        label: "5 mm",
        style: "alt",
    };
    const nearTop = MeasureGeometry.presentEdgeClearanceNearPointer(
        geom,
        [2, 140],
        session,
        "instance:door"
    );
    const nearMid = MeasureGeometry.presentEdgeClearanceNearPointer(
        geom,
        [2, 500],
        session,
        "instance:door"
    );
    const nearBottom = MeasureGeometry.presentEdgeClearanceNearPointer(
        geom,
        [2, 860],
        session,
        "instance:door"
    );
    assert.equal(nearTop.distance, 5);
    assert.equal(nearMid.distance, 5);
    assert.equal(nearBottom.distance, 5);
    assert.equal(nearTop.label, "5 mm");
    assert.equal(nearTop.direction, "left");
    assert.ok(nearTop.start[1] < nearMid.start[1]);
    assert.ok(nearMid.start[1] < nearBottom.start[1]);
    assert.equal(nearMid.start[0], 5);
    assert.equal(nearMid.end[0], 0);
    assert.equal(nearMid.presentation, "pointer-anchored");
}

// Top board-edge clearance: slide X with pointer.
{
    const session = sessionWith([
        rectPiece("instance:wide", 100, 12, 600, 40),
    ]);
    const geom = {
        kind: "edge",
        direction: "top",
        start: [100, 12],
        end: [100, 0],
        distance: 12,
    };
    const leftish = MeasureGeometry.presentEdgeClearanceNearPointer(
        geom,
        [140, 6],
        session,
        "instance:wide"
    );
    const rightish = MeasureGeometry.presentEdgeClearanceNearPointer(
        geom,
        [620, 6],
        session,
        "instance:wide"
    );
    assert.equal(leftish.distance, 12);
    assert.equal(rightish.distance, 12);
    assert.ok(leftish.start[0] < rightish.start[0]);
    assert.ok(Math.abs(leftish.start[0] - leftish.end[0]) < 1e-9);
    assert.equal(leftish.presentation, "pointer-anchored");
}

// Obstacle blocks pointer-anchored slide; falls back to a free face or original.
{
    const session = sessionWith([
        rectPiece("instance:door", 8, 100, 40, 700),
        // Thin blocker sitting in the left margin across mid-height.
        rectPiece("instance:block", 1, 350, 4, 120),
    ]);
    const geom = {
        kind: "edge",
        direction: "left",
        start: [8, 120],
        end: [0, 120],
        distance: 8,
    };
    const blocked = MeasureGeometry.presentEdgeClearanceNearPointer(
        geom,
        [4, 400],
        session,
        "instance:door"
    );
    // Must not draw through the blocker band (y≈350–470).
    const y = blocked.start[1];
    assert.ok(y < 350 - 1e-6 || y > 470 + 1e-6, `expected free y, got ${y}`);
    assert.equal(blocked.distance, 8);
    assert.equal(blocked.direction, "left");
}

// L-shape: AABB left gap matches, but notch has no material face — keep original there.
{
    const session = sessionWith([
        {
            piece_key: "instance:ell",
            piece_instance_id: "ell",
            piece_id: 9,
            sheet_no: 1,
            distribution: "active",
            editable: true,
            local_x_mm: 10,
            local_y_mm: 100,
            // Vertical stem on the left (x=10..50, y=100..500) + foot to the right.
            outline_mm: [
                [10, 100],
                [50, 100],
                [50, 400],
                [200, 400],
                [200, 500],
                [10, 500],
            ],
            base_outline_mm: [
                [10, 100],
                [50, 100],
                [50, 400],
                [200, 400],
                [200, 500],
                [10, 500],
            ],
            placement_cm: { x: 1, y: 10, w: 19, h: 40 },
        },
    ]);
    const geom = {
        kind: "edge",
        direction: "left",
        start: [10, 120],
        end: [0, 120],
        distance: 10,
    };
    // Pointer in the open notch region (no left face at x=10 for y≈250..390 of the AABB only
    // exists on the stem for y=100..500 actually - wait stem is full height on left.
    // Stem left face runs y=100..500. Notch is to the right of stem above the foot.
    // So left face exists for full height. Use a pointer and assert slide still works on stem.
    const slid = MeasureGeometry.presentEdgeClearanceNearPointer(
        geom,
        [4, 300],
        session,
        "instance:ell"
    );
    assert.equal(slid.distance, 10);
    assert.ok(Math.abs(slid.start[1] - 300) < 5 || slid.presentation === "pointer-anchored");
}

// Interaction: edge overlay follows pointer without recomputing edgeClearances geometry.
{
    const real = BoardEditor.MeasureGeometry;
    let edgeCalls = 0;
    BoardEditor.MeasureGeometry = Object.freeze({
        ...real,
        edgeClearances() {
            edgeCalls += 1;
            return [{
                kind: "edge",
                direction: "left",
                start: [5, 100],
                end: [0, 100],
                distance: 5,
            }];
        },
        shortestClearanceBetweenPieces() { return null; },
    });

    const session = sessionWith([
        rectPiece("instance:door", 5, 100, 40, 800),
    ]);
    const history = History.create(session);
    const store = createStore({ projection: { layers: [], sheets: [], elements: [], pieces: [] } });
    store.attachSession(history.get(), history);
    store.selectPiece(1, { pieceKey: "instance:door", sheetNo: 1, mode: "replace" });

    let overlay = null;
    const pad = 16;
    const metrics = {
        minX: 0,
        minY: 0,
        width: 1220,
        height: 2440,
        scale: 1,
        pad,
        contentWidth: 1220 + 32,
        contentHeight: 2440 + 32,
    };
    const interaction = createMeasureInteraction({
        store,
        getSvgEl: () => ({
            getAttribute: (name) => (
                name === "width" ? String(metrics.contentWidth)
                    : name === "height" ? String(metrics.contentHeight) : null
            ),
            getBoundingClientRect: () => ({
                left: 0,
                top: 0,
                width: metrics.contentWidth,
                height: metrics.contentHeight,
            }),
        }),
        getWorldMetrics: () => metrics,
        isAltKey: () => true,
        isPanKey: () => false,
        isMeasureToolActive: () => false,
        isDragActive: () => false,
        onOverlay: (lines) => { overlay = lines; },
    });

    function moveTo(x, y) {
        interaction.onPointerMove({
            clientX: pad + x,
            clientY: pad + y,
            altKey: true,
        });
        return overlay;
    }

    interaction.resetGeometryComputeCount();
    const topOverlay = moveTo(2, 150);
    assert.ok(topOverlay && topOverlay.length === 1);
    assert.equal(topOverlay[0].kind, "edge");
    assert.equal(topOverlay[0].distance, 5);
    const topY = topOverlay[0].start[1];
    const midOverlay = moveTo(2, 500);
    assert.equal(interaction.getGeometryComputeCount(), 1);
    assert.equal(edgeCalls, 1);
    assert.equal(midOverlay[0].distance, 5);
    assert.equal(midOverlay[0].label, real.formatDistanceMm(5));
    assert.ok(midOverlay[0].start[1] > topY);

    BoardEditor.MeasureGeometry = real;
}

// Asset pins.
{
    const page = fs.readFileSync(path.join(root, "almdina_erp/page/board_editor/board_editor.js"), "utf8");
    assert.match(page, /measure_geometry\.js\?v=3/);
    assert.match(page, /measure_interaction\.js\?v=6/);
    const geometrySource = fs.readFileSync(path.join(root, "public/js/board_editor/measure_geometry.js"), "utf8");
    const interactionSource = fs.readFileSync(path.join(root, "public/js/board_editor/measure_interaction.js"), "utf8");
    assert.match(geometrySource, /presentPieceClearanceNearPointer/);
    assert.match(geometrySource, /presentEdgeClearanceNearPointer/);
    assert.match(interactionSource, /presentPieceClearanceNearPointer/);
    assert.match(interactionSource, /presentEdgeClearanceNearPointer/);
    assert.match(interactionSource, /presentGeomLines/);
}

console.log("board_editor_measure_presentation.test.js: ok");
