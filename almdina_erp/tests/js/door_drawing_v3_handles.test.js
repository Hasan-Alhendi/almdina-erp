"use strict";

const assert = require("node:assert/strict");
const path = require("node:path");

global.window = {};
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/domain/geometry.js"));
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/application/shape_handles.js"));

const V3 = global.window.AlmdinaDoorDrawingV3;
const G = V3.Geometry;
const H = V3.ShapeHandles;

const line = G.line("L1", G.point(0, 0), G.point(100, 0));
assert.deepEqual(H.handlesFor(line).map(handle => handle.role), ["start", "end"]);
const lineResized = H.resize(line, "end", G.point(0, 150));
assert.equal(G.lineLength(lineResized), 150);
assert.equal(G.lineAngle(lineResized), 90);

const rectangle = G.rectangle("R1", G.point(0, 0), 100, 50);
assert.deepEqual(
    H.handlesFor(rectangle).map(handle => handle.role),
    ["bottom-left", "bottom-right", "top-right", "top-left"]
);
const rectResized = H.resize(rectangle, "top-right", G.point(220, 180));
assert.equal(rectResized.geometry.widthMm, 220);
assert.equal(rectResized.geometry.heightMm, 180);
assert.deepEqual(rectResized.geometry.origin, G.point(0, 0));

const rectCrossed = H.resize(rectangle, "top-left", G.point(-20, 130));
assert.deepEqual(rectCrossed.geometry.origin, G.point(-20, 0));
assert.equal(rectCrossed.geometry.widthMm, 120);
assert.equal(rectCrossed.geometry.heightMm, 130);

const square = H.resize(rectangle, "top-right", G.point(240, 90), { square: true });
assert.equal(square.geometry.widthMm, 240);
assert.equal(square.geometry.heightMm, 240, "Shift resize keeps an exact square around the opposite corner");

const circle = G.circle("C1", G.point(100, 100), 50);
const circleHandles = H.handlesFor(circle);
assert.deepEqual(circleHandles.map(handle => handle.role), ["center", "east", "north", "west", "south"]);
assert.equal(H.handleByRole(circle, "east").axis, "horizontal");
assert.equal(H.handleByRole(circle, "north").axis, "vertical");
const circleRadius = H.resize(circle, "east", G.point(250, 100));
assert.equal(circleRadius.geometry.radiusMm, 150);
const circleMoved = H.resize(circle, "center", G.point(400, 450));
assert.deepEqual(circleMoved.geometry.center, G.point(400, 450));
assert.equal(circleMoved.geometry.radiusMm, 50);

const arc = G.arc("A1", G.point(0, 0), 100, 0, 90);
assert.deepEqual(H.handlesFor(arc).map(handle => handle.role), ["center", "start", "end", "radius"]);
const arcStart = H.resize(arc, "start", G.pointAt(G.point(0, 0), 100, 45));
assert.equal(arcStart.geometry.startAngleDeg, 45);
assert.equal(arcStart.geometry.sweepAngleDeg, 45, "Dragging arc start preserves the former end point and sweep direction");
assert.deepEqual(G.arcEnd(arcStart), G.point(0, 100));

const arcEnd = H.resize(arc, "end", G.point(-100, 0));
assert.equal(arcEnd.geometry.sweepAngleDeg, 180);
assert.deepEqual(G.arcStart(arcEnd), G.point(100, 0));
assert.deepEqual(G.arcEnd(arcEnd), G.point(-100, 0));

const arcRadius = H.resize(arc, "radius", G.point(200, 0));
assert.equal(arcRadius.geometry.radiusMm, 200);
assert.equal(G.arcLength(arcRadius), 314.159);
const arcMoved = H.resize(arc, "center", G.point(500, 600));
assert.deepEqual(arcMoved.geometry.center, G.point(500, 600));
assert.equal(arcMoved.geometry.radiusMm, 100);
assert.equal(arcMoved.geometry.startAngleDeg, 0);
assert.equal(arcMoved.geometry.sweepAngleDeg, 90);

const clockwise = G.arc("A2", G.point(0, 0), 100, 90, -90);
const clockwiseEnd = H.resize(clockwise, "end", G.pointAt(G.point(0, 0), 100, -45));
assert.ok(clockwiseEnd.geometry.sweepAngleDeg < 0, "Arc endpoint edits preserve clockwise/counter-clockwise direction");

assert.throws(() => H.resize(circle, "unknown", G.point(0, 0)));
assert.throws(() => H.resize(arc, "unknown", G.point(0, 0)));

console.log("Door Drawing V3 shape handle tests passed");
