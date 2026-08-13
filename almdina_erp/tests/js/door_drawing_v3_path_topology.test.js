"use strict";

const assert = require("node:assert/strict");
const path = require("node:path");

global.window = {};
const load = file => require(path.resolve(__dirname, `../../public/js/door_drawing_v3/${file}`));
load("domain/geometry.js");
load("domain/document.js");
load("domain/smart_path_domain.js");
load("domain/bezier_path_domain.js");
load("domain/path_topology_domain.js");

const V3 = global.window.AlmdinaDoorDrawingV3;
const G = V3.Geometry;
const T = V3.PathTopologyDomain;
const near = (actual, expected, tolerance = 0.08) => assert.ok(Math.abs(actual - expected) <= tolerance, `${actual} ~= ${expected}`);

const curve = G.path("curve", [G.point(0, 0), G.point(100, 0)], false, {}, [
    { type: G.NODE_SMOOTH, out: { x: 0, y: 100 } },
    { type: G.NODE_SMOOTH, in: { x: 0, y: 100 } },
]);
const snapshot = JSON.stringify(curve);
const reversed = T.reversePath(curve);
assert.deepEqual(reversed.geometry.points, [G.point(100, 0), G.point(0, 0)]);
assert.deepEqual(G.pathNode(reversed, 0).out, G.pathNode(curve, 1).in);
assert.deepEqual(G.pathNode(reversed, 1).in, G.pathNode(curve, 0).out);
near(G.pathLength(reversed), G.pathLength(curve));
assert.equal(JSON.stringify(curve), snapshot, "reverse must not mutate source geometry");

const closed = G.path("closed", [G.point(0, 0), G.point(100, 0), G.point(60, 80)], true, {}, [
    { type: G.NODE_CORNER, in: { x: -20, y: 10 }, out: { x: 25, y: 20 } },
    { type: G.NODE_SMOOTH, in: { x: -25, y: 20 }, out: { x: 10, y: 20 } },
    { type: G.NODE_CORNER, in: { x: 15, y: -20 }, out: { x: -15, y: -20 } },
]);
const reversedClosed = T.reversePath(closed);
assert.equal(reversedClosed.geometry.closed, true);
assert.deepEqual(reversedClosed.geometry.points[0], closed.geometry.points[0], "closed reverse keeps stable first anchor");
near(G.pathLength(reversedClosed), G.pathLength(closed));

const opened = T.openPath(closed, 1);
assert.equal(opened.geometry.closed, false);
assert.deepEqual(opened.geometry.points[0], closed.geometry.points[1]);
assert.equal(G.pathNode(opened, 0).in, null);
assert.equal(G.pathNode(opened, opened.geometry.points.length - 1).out, null);
const reclosed = T.closePath(opened);
assert.equal(reclosed.geometry.closed, true);
assert.deepEqual(G.pathNode(reclosed, 1), G.pathNode(opened, 1), "close retains interior handles");

const parts = T.splitPathAtSegmentMidpoint(curve, 0, "curve-right");
assert.equal(parts.length, 2);
assert.equal(parts[0].id, "curve");
assert.equal(parts[1].id, "curve-right");
assert.deepEqual(parts[0].geometry.points.at(-1), parts[1].geometry.points[0]);
assert.equal(G.pathSegment(parts[0], 0).curved, true);
assert.equal(G.pathSegment(parts[1], 0).curved, true);
near(G.pathLength(parts[0]) + G.pathLength(parts[1]), G.pathLength(curve));

const cutClosed = T.splitPathAtNode(closed, 1, "unused");
assert.equal(cutClosed.length, 1);
assert.equal(cutClosed[0].geometry.closed, false);
assert.equal(cutClosed[0].geometry.points.length, closed.geometry.points.length + 1);
assert.deepEqual(cutClosed[0].geometry.points[0], closed.geometry.points[1]);
assert.deepEqual(cutClosed[0].geometry.points.at(-1), closed.geometry.points[1]);
near(G.pathLength(cutClosed[0]), G.pathLength(closed));

const left = G.path("left", [G.point(0, 0), G.point(50, 0)], false, {}, [
    { out: { x: 15, y: 20 } }, { in: { x: -15, y: 20 } },
]);
const right = G.path("right", [G.point(100, 0), G.point(50, 0)], false, {}, [
    { out: { x: -15, y: -20 } }, { in: { x: 15, y: -20 } },
]);
const joined = T.joinOpenPaths(left, right);
assert.equal(joined.gapMm, 0);
assert.equal(joined.object.geometry.points.length, 3);
assert.deepEqual(joined.object.geometry.points[1], G.point(50, 0));
assert.ok(G.pathNode(joined.object, 1).in);
assert.ok(G.pathNode(joined.object, 1).out);

const gapLeft = G.path("gap-left", [G.point(0, 0), G.point(40, 0)], false);
const gapRight = G.path("gap-right", [G.point(60, 0), G.point(100, 0)], false);
const gapLeftBefore = JSON.stringify(gapLeft.geometry.points);
const gapRightBefore = JSON.stringify(gapRight.geometry.points);
const gapJoin = T.joinOpenPaths(gapLeft, gapRight);
assert.equal(gapJoin.gapMm, 20);
assert.deepEqual(gapJoin.object.geometry.points, [G.point(0, 0), G.point(40, 0), G.point(60, 0), G.point(100, 0)]);
assert.equal(JSON.stringify(gapLeft.geometry.points), gapLeftBefore, "join does not move first source path");
assert.equal(JSON.stringify(gapRight.geometry.points), gapRightBefore, "join does not move second source path");

console.log("Door Drawing V3 Bezier-safe path topology tests passed");