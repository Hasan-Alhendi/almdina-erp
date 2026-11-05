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
assert.equal(typeof MeasureGeometry.facingCorridor, "function");

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

// Asset pins.
{
    const page = fs.readFileSync(path.join(root, "almdina_erp/page/board_editor/board_editor.js"), "utf8");
    assert.match(page, /measure_geometry\.js\?v=2/);
    assert.match(page, /measure_interaction\.js\?v=5/);
    const geometrySource = fs.readFileSync(path.join(root, "public/js/board_editor/measure_geometry.js"), "utf8");
    const interactionSource = fs.readFileSync(path.join(root, "public/js/board_editor/measure_interaction.js"), "utf8");
    assert.match(geometrySource, /presentPieceClearanceNearPointer/);
    assert.match(interactionSource, /presentPieceClearanceNearPointer/);
    assert.match(interactionSource, /presentGeomLines/);
}

console.log("board_editor_measure_presentation.test.js: ok");
