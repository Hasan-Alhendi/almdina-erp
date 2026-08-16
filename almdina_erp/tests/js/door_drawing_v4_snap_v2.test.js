"use strict";

const assert = require("node:assert/strict");
const path = require("node:path");

global.window = {};
const load = file => require(path.resolve(__dirname, `../../public/js/door_drawing_v4/${file}`));
load("domain/geometry.js");
load("domain/document.js");
load("application/snap_resolver.js");
load("application/viewport.js");

const V4 = global.window.AlmdinaDoorDrawingV4;
const G = V4.Geometry;
const D = V4.DocumentModel;
const S = V4.SnapResolver;
const Viewport = V4.Viewport;

function documentWith(nodes = [], segments = []) {
    return D.create({
        widthMm: 500,
        heightMm: 500,
        nodes,
        segments: segments.map(segment => ({ type: "line", ...segment })),
        paths: [],
    });
}

// Endpoint is a real topological snap and outranks an angle guide.
let document = documentWith([{ id: "n1", xMm: 100, yMm: 0 }]);
let snap = S.resolve(document, {
    rawPoint: G.point(99, 1),
    origin: G.point(0, 0),
    toleranceMm: 3,
});
assert.equal(snap.type, "endpoint");
assert.equal(snap.nodeId, "n1");
assert.deepEqual(snap.point, G.point(100, 0));

// Close is stronger than the same node as a normal endpoint.
snap = S.resolve(document, {
    rawPoint: G.point(99, 1),
    origin: G.point(0, 50),
    toleranceMm: 3,
    canClose: true,
    closeNodeId: "n1",
});
assert.equal(snap.type, "close");
assert.equal(snap.semantic, "close");
assert.equal(snap.nodeId, "n1");

// Midpoint snaps geometrically but must not fake shared-node topology.
document = documentWith(
    [
        { id: "a", xMm: 0, yMm: 0 },
        { id: "b", xMm: 100, yMm: 0 },
    ],
    [{ id: "s1", startNodeId: "a", endNodeId: "b" }]
);
snap = S.resolve(document, { rawPoint: G.point(50, 2), toleranceMm: 3 });
assert.equal(snap.type, "midpoint");
assert.deepEqual(snap.point, G.point(50, 0));
assert.equal(snap.nodeId, null);
assert.equal(snap.segmentId, "s1");

// Edge snap works anywhere inside an existing line without inventing topology.
snap = S.resolve(document, { rawPoint: G.point(25, 2), toleranceMm: 3 });
assert.equal(snap.type, "edge");
assert.deepEqual(snap.point, G.point(25, 0));
assert.equal(snap.nodeId, null);
assert.equal(snap.segmentId, "s1");

// Existing line-line intersection is exact and remains geometric-only until Split Segment exists.
document = documentWith(
    [
        { id: "a", xMm: 0, yMm: 0 },
        { id: "b", xMm: 100, yMm: 100 },
        { id: "c", xMm: 0, yMm: 100 },
        { id: "d", xMm: 100, yMm: 0 },
    ],
    [
        { id: "s1", startNodeId: "a", endNodeId: "b" },
        { id: "s2", startNodeId: "c", endNodeId: "d" },
    ]
);
snap = S.resolve(document, { rawPoint: G.point(51, 49), toleranceMm: 3 });
assert.equal(snap.type, "intersection");
assert.deepEqual(snap.point, G.point(50, 50));
assert.equal(snap.nodeId, null);

// Live intersection projects the current pen direction into an existing segment.
document = documentWith(
    [
        { id: "a", xMm: 40, yMm: 50 },
        { id: "b", xMm: 100, yMm: 50 },
    ],
    [{ id: "s1", startNodeId: "a", endNodeId: "b" }]
);
snap = S.resolve(document, {
    rawPoint: G.point(52, 52),
    origin: G.point(0, 0),
    toleranceMm: 3,
});
assert.equal(snap.type, "intersection");
assert.deepEqual(snap.point, G.point(50, 50));
assert.equal(snap.nodeId, null);
assert.equal(snap.referenceSegmentId, "s1");

// Perpendicular foot onto an existing segment outranks the generic edge projection.
document = documentWith(
    [
        { id: "a", xMm: 0, yMm: 100 },
        { id: "b", xMm: 100, yMm: 100 },
    ],
    [{ id: "s1", startNodeId: "a", endNodeId: "b" }]
);
snap = S.resolve(document, {
    rawPoint: G.point(31, 99),
    origin: G.point(30, 0),
    toleranceMm: 3,
});
assert.equal(snap.type, "perpendicular");
assert.deepEqual(snap.point, G.point(30, 100));
assert.equal(snap.referenceSegmentId, "s1");

// Parallel guide outranks a generic vertical angle guide.
document = documentWith(
    [
        { id: "a", xMm: 100, yMm: 0 },
        { id: "b", xMm: 100, yMm: 100 },
    ],
    [{ id: "s1", startNodeId: "a", endNodeId: "b" }]
);
snap = S.resolve(document, {
    rawPoint: G.point(2, 70),
    origin: G.point(0, 0),
    toleranceMm: 3,
});
assert.equal(snap.type, "parallel");
assert.deepEqual(snap.point, G.point(0, 70));

// Extension projects beyond a real segment endpoint.
document = documentWith(
    [
        { id: "a", xMm: 0, yMm: 0 },
        { id: "b", xMm: 100, yMm: 0 },
    ],
    [{ id: "s1", startNodeId: "a", endNodeId: "b" }]
);
snap = S.resolve(document, { rawPoint: G.point(130, 2), toleranceMm: 3 });
assert.equal(snap.type, "extension");
assert.deepEqual(snap.point, G.point(130, 0));

// 45-degree family remains available when no stronger geometric relation exists.
document = documentWith();
snap = S.resolve(document, {
    rawPoint: G.point(100, 2),
    origin: G.point(0, 0),
    toleranceMm: 3,
});
assert.equal(snap.type, "angle");
assert.equal(snap.semantic, "horizontal");
assert.deepEqual(snap.point, G.point(Math.hypot(100, 2), 0));

// Grid is a low-priority spatial fallback and never pretends to share a node.
snap = S.resolve(document, {
    rawPoint: G.point(49, 52),
    toleranceMm: 3,
    gridStepMm: 50,
});
assert.equal(snap.type, "grid");
assert.deepEqual(snap.point, G.point(50, 50));
assert.equal(snap.nodeId, null);

// A meaningful angle relation outranks the grid fallback.
snap = S.resolve(document, {
    rawPoint: G.point(49, 2),
    origin: G.point(0, 0),
    toleranceMm: 3,
    gridStepMm: 50,
});
assert.equal(snap.type, "angle");
assert.equal(snap.semantic, "horizontal");

// Magnetic hysteresis: acquire inside 10px-equivalent radius, retain inside 14px-equivalent radius, then release.
document = documentWith([{ id: "n1", xMm: 100, yMm: 0 }]);
const acquired = S.resolve(document, { rawPoint: G.point(102, 0), toleranceMm: 3, releaseToleranceMm: 5 });
assert.equal(acquired.type, "endpoint");
const retained = S.resolve(document, {
    rawPoint: G.point(104, 0),
    toleranceMm: 3,
    releaseToleranceMm: 5,
    previousSnap: acquired,
});
assert.equal(retained.type, "endpoint");
assert.equal(retained.key, acquired.key);
const released = S.resolve(document, {
    rawPoint: G.point(106, 0),
    toleranceMm: 3,
    releaseToleranceMm: 5,
    previousSnap: retained,
});
assert.equal(released.type, "free");

// Deterministic tie-break: identical distances resolve by stable candidate key.
document = documentWith([
    { id: "b", xMm: 100, yMm: 1 },
    { id: "a", xMm: 100, yMm: -1 },
]);
snap = S.resolve(document, { rawPoint: G.point(100, 0), toleranceMm: 2 });
assert.equal(snap.type, "endpoint");
assert.equal(snap.nodeId, "a");

// Screen-space contract: acquire/release radii and adaptive grid remain stable as zoom changes.
let camera = Viewport.create({ scalePxPerMm: 1 });
assert.equal(Viewport.screenToleranceToMm(camera, 10), 10);
assert.equal(Viewport.screenToleranceToMm(camera, 14), 14);
assert.equal(Viewport.gridStepMm(camera), 50);
camera = Viewport.create({ scalePxPerMm: 2 });
assert.equal(Viewport.screenToleranceToMm(camera, 10), 5);
assert.equal(Viewport.screenToleranceToMm(camera, 14), 7);
assert.equal(Viewport.gridStepMm(camera), 20);

console.log("Door Drawing V4 Smart Snap V2 tests passed");
