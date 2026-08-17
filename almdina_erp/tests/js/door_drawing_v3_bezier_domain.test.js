"use strict";

const assert = require("node:assert/strict");
const path = require("node:path");

global.window = {};
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/domain/geometry.js"));
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/domain/document.js"));
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/domain/smart_path_domain.js"));
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/domain/bezier_path_domain.js"));
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/domain/vector_selection.js"));
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/domain/bezier_selection_domain.js"));

const V3 = global.window.AlmdinaDoorDrawingV3;
const G = V3.Geometry;
const D = V3.DocumentModel;
const Selection = V3.VectorSelectionGeometry;

function near(actual, expected, tolerance = 0.02, message = "") {
    assert.ok(Math.abs(actual - expected) <= tolerance, `${message} expected ${expected}, got ${actual}`);
}

const legacy = G.path("legacy", [G.point(0, 0), G.point(100, 0)], false);
assert.equal(G.pathNodes(legacy).length, 2);
assert.equal(G.pathNode(legacy, 0).type, G.NODE_CORNER);
assert.equal(G.pathSegment(legacy, 0).curved, false);

const curved = G.path("curve", [G.point(0, 0), G.point(100, 0)], false, {}, [
    { type: G.NODE_SMOOTH, out: { x: 0, y: 100 } },
    { type: G.NODE_SMOOTH, in: { x: 0, y: 100 } },
]);
assert.equal(G.pathSegment(curved, 0).curved, true);
const midpoint = G.pathPointAtSegment(curved, 0, 0.5);
near(midpoint.x, 50, 0.01, "Bezier midpoint x");
near(midpoint.y, 75, 0.01, "Bezier midpoint y");
const curveBounds = G.pathBounds(curved);
near(curveBounds.left, 0);
near(curveBounds.right, 100);
near(curveBounds.bottom, 75, 0.02, "Cubic bounds must use extrema rather than control points");
assert.deepEqual(Selection.boundsOfObject(curved), {
    left: 0, top: 0, right: 100, bottom: 75, width: 100, height: 75, cx: 50, cy: 37.5,
});
assert.deepEqual(Selection.midpointOfSegment(curved, 0), midpoint);

const split = G.splitPathSegment(curved, 0, 0.5);
assert.equal(split.geometry.points.length, 3);
assert.equal(G.pathNode(split, 1).type, G.NODE_SMOOTH);
const originalQuarter = G.pathPointAtSegment(curved, 0, 0.25);
const splitQuarter = G.pathPointAtSegment(split, 0, 0.5);
near(splitQuarter.x, originalQuarter.x, 0.02, "De Casteljau split x");
near(splitQuarter.y, originalQuarter.y, 0.02, "De Casteljau split y");
const originalThreeQuarter = G.pathPointAtSegment(curved, 0, 0.75);
const splitThreeQuarter = G.pathPointAtSegment(split, 1, 0.5);
near(splitThreeQuarter.x, originalThreeQuarter.x, 0.02, "De Casteljau second half x");
near(splitThreeQuarter.y, originalThreeQuarter.y, 0.02, "De Casteljau second half y");

const lineToCurve = G.convertPathSegment(legacy, 0, "curve");
assert.equal(G.pathSegment(lineToCurve, 0).curved, true);
near(G.pathNode(lineToCurve, 0).out.x, 100 / 3, 0.02);
near(G.pathNode(lineToCurve, 1).in.x, -100 / 3, 0.02);
assert.equal(G.pathSegment(G.convertPathSegment(lineToCurve, 0, "line"), 0).curved, false);

let symmetric = G.path("sym", [G.point(0, 0), G.point(100, 0), G.point(200, 0)], false, {}, [
    {},
    { type: G.NODE_SYMMETRIC, in: { x: -20, y: 0 }, out: { x: 20, y: 0 } },
    {},
]);
symmetric = G.setPathHandle(symmetric, 1, "out", G.point(100, 30));
near(G.pathNode(symmetric, 1).out.x, 0);
near(G.pathNode(symmetric, 1).out.y, 30);
near(G.pathNode(symmetric, 1).in.x, 0);
near(G.pathNode(symmetric, 1).in.y, -30);
const broken = G.setPathHandle(symmetric, 1, "out", G.point(130, 30), { breakTangency: true });
assert.equal(G.pathNode(broken, 1).type, G.NODE_CORNER);
near(G.pathNode(broken, 1).in.y, -30, 0.02, "Alt/break tangency keeps the opposite handle independent");

const moved = G.movePathNodes(curved, [0], 10, 20);
assert.deepEqual(moved.geometry.points[0], G.point(10, 20));
assert.deepEqual(G.pathNode(moved, 0).out, G.pathNode(curved, 0).out, "Node movement preserves relative handles");
const translated = G.translateObject(curved, 25, -10);
assert.deepEqual(G.pathNode(translated, 0).out, G.pathNode(curved, 0).out, "Object movement preserves Bezier metadata");

const flattened = G.flattenPath(curved, 0.2);
assert.ok(flattened.length > 4, "Curves are flattened into enough points for legacy/DXF compatibility");
assert.ok(G.pathLength(curved) > 100, "Bezier length follows the curve, not its chord");

let document = D.create({ widthMm: 300, heightMm: 300 });
document = D.addObject(document, curved);
const restored = D.normalize(JSON.parse(D.serialize(document)));
const restoredCurve = D.objectById(restored, "curve");
assert.deepEqual(G.pathNode(restoredCurve, 0).out, G.pathNode(curved, 0).out, "Persistence keeps Bezier handles");
assert.equal(G.pathNode(restoredCurve, 0).type, G.NODE_SMOOTH);

console.log("Door Drawing V3 Bezier domain tests passed");
