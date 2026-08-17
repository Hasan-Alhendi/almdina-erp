"use strict";

const assert = require("node:assert/strict");
const path = require("node:path");

global.window = {};
const load = file => require(path.resolve(__dirname, `../../public/js/door_drawing_v4/${file}`));
load("domain/geometry.js");
load("domain/document.js");
load("application/viewport.js");

global.window.AlmdinaDoorDrawingV4.CanvasRenderer = Object.freeze({
    TOKENS: Object.freeze({}),
    resizeCanvas() {},
    render() {},
});
load("presentation/selection_overlay.js");

const V4 = global.window.AlmdinaDoorDrawingV4;
const D = V4.DocumentModel;
const Overlay = V4.SelectionOverlay;

const document = D.create({
    widthMm: 1220,
    heightMm: 2440,
    nodes: [
        { id: "n1", xMm: 100, yMm: 200 },
        { id: "n2", xMm: 700, yMm: 200 },
        { id: "n3", xMm: 700, yMm: 1400 },
        { id: "n4", xMm: 100, yMm: 1400 },
    ],
    segments: [
        { id: "s1", startNodeId: "n1", endNodeId: "n2" },
        { id: "s2", startNodeId: "n2", endNodeId: "n3" },
        { id: "s3", startNodeId: "n3", endNodeId: "n4" },
        { id: "s4", startNodeId: "n4", endNodeId: "n1" },
    ],
    paths: [{ id: "p1", startNodeId: "n1", segmentIds: ["s1", "s2", "s3", "s4"], closed: true }],
});

const bounds = Overlay.selectionBounds(document, { kind: "path", id: "p1" });
assert.deepEqual(bounds, {
    minX: 100,
    minY: 200,
    maxX: 700,
    maxY: 1400,
    widthMm: 600,
    heightMm: 1200,
});
assert.equal(Overlay.selectionBounds(document, null), null);
assert.equal(Overlay.selectionBounds(document, { kind: "node", id: "n1" }), null);
assert.equal(Overlay.selectionBounds(document, { kind: "path", id: "missing" }), null);
assert.notEqual(V4.CanvasRenderer.render, undefined, "Selection overlay must preserve the renderer contract");

console.log("Door Drawing V4 Figma selection overlay tests passed");
