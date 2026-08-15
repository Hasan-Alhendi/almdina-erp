"use strict";

const assert = require("node:assert/strict");
const path = require("node:path");

global.window = {};
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/domain/geometry.js"));
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/domain/document.js"));
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/domain/smart_path_domain.js"));
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/domain/bezier_path_domain.js"));
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/domain/boolean_geometry_domain.js"));

const V3 = global.window.AlmdinaDoorDrawingV3;
const G = V3.Geometry;
const B = V3.BooleanGeometryDomain;

function near(actual, expected, tolerance = 0.2, message = "") {
    assert.ok(Math.abs(actual - expected) <= tolerance, `${message} expected ${expected}, got ${actual}`);
}
function totalArea(result) {
    return result.contours.reduce((sum, contour) => sum + B.signedArea(contour), 0);
}

assert.equal(B.DEFAULT_TOLERANCE_MM, 0.05);
assert.deepEqual(B.OPERATIONS, ["union", "subtract", "intersect", "exclude"]);

const a = G.rectangle("a", G.point(0, 0), 100, 100);
const b = G.rectangle("b", G.point(50, 0), 100, 100);

const union = B.booleanContours(a, b, "union");
assert.equal(union.ok, true);
assert.equal(union.contours.length, 1);
near(Math.abs(totalArea(union)), 15000, 0.1, "overlap union area");

const intersection = B.booleanContours(a, b, "intersect");
assert.equal(intersection.ok, true);
assert.equal(intersection.contours.length, 1);
near(Math.abs(totalArea(intersection)), 5000, 0.1, "overlap intersection area");

const subtraction = B.booleanContours(a, b, "subtract");
assert.equal(subtraction.ok, true);
assert.equal(subtraction.contours.length, 1);
near(Math.abs(totalArea(subtraction)), 5000, 0.1, "overlap subtraction area");

const exclude = B.booleanContours(a, b, "exclude");
assert.equal(exclude.ok, true);
assert.equal(exclude.contours.length, 2);
near(Math.abs(totalArea(exclude)), 10000, 0.1, "overlap exclude area");

const outer = G.rectangle("outer", G.point(0, 0), 100, 100);
const inner = G.rectangle("inner", G.point(20, 20), 20, 20);
const hole = B.booleanContours(outer, inner, "subtract");
assert.equal(hole.ok, true);
assert.equal(hole.contours.length, 2, "contained subtraction must retain an outer contour and a hole contour");
near(Math.abs(totalArea(hole)), 9600, 0.1, "contained subtraction signed area");
assert.ok(hole.contours.some(contour => B.signedArea(contour) > 0));
assert.ok(hole.contours.some(contour => B.signedArea(contour) < 0), "hole contour must keep opposite winding");

const far = G.rectangle("far", G.point(200, 0), 50, 50);
const disjointUnion = B.booleanContours(a, far, "union");
assert.equal(disjointUnion.contours.length, 2, "union of disconnected shapes remains two real contours");
near(Math.abs(totalArea(disjointUnion)), 12500, 0.1);
const disjointIntersection = B.booleanContours(a, far, "intersect");
assert.equal(disjointIntersection.ok, true);
assert.equal(disjointIntersection.contours.length, 0);

const circle = G.circle("circle", G.point(50, 50), 30);
const circlePolygon = B.objectToPolygon(circle);
assert.equal(circlePolygon.approximated, true);
assert.ok(circlePolygon.points.length >= 24);
const circleUnion = B.booleanContours(circle, G.rectangle("circle-box", G.point(50, 20), 40, 60), "union");
assert.equal(circleUnion.ok, true);
assert.ok(circleUnion.contours.length >= 1);
assert.equal(circleUnion.approximated, true);

const curved = G.path("curved", [
    G.point(0, 0), G.point(100, 0), G.point(100, 100), G.point(0, 100),
], true, {}, [
    { type: G.NODE_SMOOTH, out: { x: 20, y: -25 } },
    { type: G.NODE_SMOOTH, in: { x: -20, y: -25 } },
    {}, {},
]);
const curvedPolygon = B.objectToPolygon(curved);
assert.equal(curvedPolygon.approximated, true);
assert.ok(curvedPolygon.points.length > curved.geometry.points.length, "Bezier operand must be adaptively flattened at the documented tolerance");
const curvedIntersection = B.booleanContours(curved, G.rectangle("clip", G.point(25, -10), 50, 120), "intersect");
assert.equal(curvedIntersection.ok, true);
assert.equal(curvedIntersection.approximated, true);
assert.ok(curvedIntersection.contours.length >= 1);

const bowtie = G.path("bowtie", [
    G.point(0, 0), G.point(100, 100), G.point(0, 100), G.point(100, 0),
], true);
const rejected = B.booleanContours(bowtie, a, "union");
assert.equal(rejected.ok, false);
assert.equal(rejected.reason, "self_intersection");

const openPath = G.path("open", [G.point(0, 0), G.point(100, 0)], false);
assert.equal(B.isBooleanOperand(openPath), false);
assert.equal(B.booleanContours(openPath, a, "union").reason, "unsupported_operand");

console.log("Door Drawing V3 Boolean geometry tests passed");
