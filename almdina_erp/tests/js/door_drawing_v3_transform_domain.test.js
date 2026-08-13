"use strict";

const assert = require("node:assert/strict");
const path = require("node:path");

global.window = {};
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/domain/geometry.js"));
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/domain/document.js"));
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/domain/smart_path_domain.js"));
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/domain/bezier_path_domain.js"));
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/domain/transform_domain.js"));

const V3 = global.window.AlmdinaDoorDrawingV3;
const G = V3.Geometry;
const T = V3.TransformDomain;

function close(actual, expected, epsilon = 0.002, message = "") {
    assert.ok(Math.abs(actual - expected) <= epsilon, message || `${actual} ≈ ${expected}`);
}
function pointClose(actual, expected, epsilon = 0.002) {
    close(actual.x, expected.x, epsilon);
    close(actual.y, expected.y, epsilon);
}

const p = G.point(10, 20);
pointClose(T.transformPoint(p, T.translation(5, -3)), G.point(15, 17));
pointClose(T.transformPoint(p, T.scaleAround(G.point(0, 0), 2, 3)), G.point(20, 60));
pointClose(T.transformPoint(G.point(10, 0), T.rotateAround(G.point(0, 0), 90)), G.point(0, 10));

const rectangle = G.rectangle("rect", G.point(10, 20), 40, 30);
const scaledRectangle = T.transformObject(rectangle, T.scaleAround(G.point(10, 20), 2, 0.5));
assert.equal(scaledRectangle.type, "rectangle", "Axis-aligned resize should preserve rectangle semantics");
pointClose(scaledRectangle.geometry.origin, G.point(10, 20));
close(scaledRectangle.geometry.widthMm, 80);
close(scaledRectangle.geometry.heightMm, 15);

const reflectedRectangle = T.transformObject(rectangle, T.scaleAround(G.point(30, 35), -1, 1));
assert.equal(reflectedRectangle.type, "rectangle", "Axis-aligned reflection should remain a rectangle");
pointClose(reflectedRectangle.geometry.origin, G.point(10, 20));
close(reflectedRectangle.geometry.widthMm, 40);
close(reflectedRectangle.geometry.heightMm, 30);

const rotatedRectangle = T.transformObject(rectangle, T.rotateAround(G.point(30, 35), 30));
assert.equal(rotatedRectangle.type, G.PATH_TYPE, "Rotated rectangle should become editable path geometry rather than storing presentation-only rotation");
assert.equal(rotatedRectangle.geometry.closed, true);
assert.equal(rotatedRectangle.geometry.points.length, 4);

const circle = G.circle("circle", G.point(100, 100), 25);
const uniformCircle = T.transformObject(circle, T.scaleAround(G.point(100, 100), 2, 2));
assert.equal(uniformCircle.type, "circle", "Uniform scaling should preserve circle semantics");
pointClose(uniformCircle.geometry.center, G.point(100, 100));
close(uniformCircle.geometry.radiusMm, 50);

const ellipsePath = T.transformObject(circle, T.scaleAround(G.point(100, 100), 2, 1));
assert.equal(ellipsePath.type, G.PATH_TYPE, "Non-uniform circle scaling should become an exact Bezier ellipse path");
assert.equal(ellipsePath.geometry.closed, true);
assert.equal(ellipsePath.geometry.points.length, 4);
assert.ok(G.pathSegments(ellipsePath).every(segment => segment.curved), "Ellipse path should retain cubic handles on every quarter");

const arc = G.arc("arc", G.point(0, 0), 50, 0, 90);
const flippedArc = T.transformObject(arc, T.scaleAround(G.point(0, 0), -1, 1));
assert.equal(flippedArc.type, "arc");
close(flippedArc.geometry.radiusMm, 50);
close(flippedArc.geometry.sweepAngleDeg, -90, 0.002, "Reflection must reverse arc sweep direction");
pointClose(G.arcStart(flippedArc), G.point(-50, 0));

const bezier = G.path(
    "bezier",
    [G.point(0, 0), G.point(100, 0)],
    false,
    {},
    [
        { type: G.NODE_SMOOTH, out: { x: 30, y: 40 } },
        { type: G.NODE_SMOOTH, in: { x: -30, y: 40 } },
    ]
);
const transformedBezier = T.transformObject(bezier, T.scaleAround(G.point(0, 0), 2, 0.5));
assert.equal(transformedBezier.type, G.PATH_TYPE);
pointClose(transformedBezier.geometry.points[1], G.point(200, 0));
const transformedNodes = G.pathNodes(transformedBezier);
close(transformedNodes[0].out.x, 60);
close(transformedNodes[0].out.y, 20);
close(transformedNodes[1].in.x, -60);
close(transformedNodes[1].in.y, 20);

const bounds = Object.freeze({ left: 0, top: 0, right: 100, bottom: 50, width: 100, height: 50, cx: 50, cy: 25 });
pointClose(T.transformPoint(G.point(10, 20), T.flipHorizontal(bounds)), G.point(90, 20));
pointClose(T.transformPoint(G.point(10, 20), T.flipVertical(bounds)), G.point(10, 30));

assert.equal(T.similarityScale(T.rotation(33)), 1, "Rotation must be recognized as a similarity transform");
assert.equal(T.similarityScale(T.scaling(2, 1)), null, "Non-uniform scale must not be treated as a similarity transform");

console.log("Door Drawing V3 affine transform domain tests passed");
