"use strict";

const assert = require("node:assert/strict");
const path = require("node:path");

global.window = {};
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/domain/geometry.js"));
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/application/smart_freehand_policy.js"));
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/application/smart_stroke_intelligence.js"));
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/application/smart_stroke_corner_guard.js"));

const V3 = global.window.AlmdinaDoorDrawingV3;
const G = V3.Geometry;
const I = V3.SmartStrokeIntelligence;

const mouseState = I.createStabilizer("mouse", G.point(0, 0));
const penState = I.createStabilizer("pen", G.point(0, 0));
const mousePoint = I.pushStabilized(mouseState, G.point(10, 0), { motionScaleMm: 20 });
const penPoint = I.pushStabilized(penState, G.point(10, 0), { motionScaleMm: 20 });
assert.ok(mousePoint.x < penPoint.x, "Mouse preview should suppress hand jitter more aggressively than pen input");
assert.ok(penPoint.x < 10, "Pen input still receives light stabilization instead of bypassing the shared pipeline");

const mouseSeries = I.stabilizeSeries([
    G.point(0, 0), G.point(10, 2), G.point(20, -2), G.point(30, 1.5), G.point(40, 0),
], "mouse", { motionScaleMm: 18 });
assert.deepEqual(mouseSeries[0], G.point(0, 0));
assert.deepEqual(mouseSeries.at(-1), G.point(40, 0), "Live stabilization must preserve exact gesture endpoints for snapping/connection");

const roughRightAngle = [];
for (let x = 0; x <= 100; x += 5) roughRightAngle.push(G.point(x, x % 10 === 0 ? 0.45 : -0.4));
for (let y = 5; y <= 100; y += 5) roughRightAngle.push(G.point(y % 10 === 0 ? 100.45 : 99.55, y));
const mixed = I.interpret(roughRightAngle, {
    closed: false,
    straightToleranceMm: 2.4,
    simplifyToleranceMm: 1.2,
    straightRatio: 1.07,
    arcResidualRatio: 0.04,
    minimumSegmentMm: 20,
    smoothingPasses: 2,
    pathSmoothingPasses: 1,
    orthogonalAngleToleranceDeg: 10,
    preserveEndpoints: true,
    orthogonalize: true,
});
assert.equal(mixed.type, "compound", "One mouse drag containing a clear corner should split into intelligent geometry runs");
assert.equal(mixed.segments.length, 2);
assert.deepEqual(mixed.segments.map(segment => segment.type), ["line", "line"]);
assert.deepEqual(mixed.segments[0].end, mixed.segments[1].start, "Split runs must share the exact same world-mm junction");
assert.ok(mixed.cornerTurnDeg > 70, "The corner guard should only activate for a clearly deliberate change in direction");

const arcPoints = [];
for (let angle = -90; angle <= 10; angle += 5) {
    const radius = 80 + (angle % 10 === 0 ? 0.25 : -0.2);
    arcPoints.push(G.pointAt(G.point(200, 200), radius, angle));
}
const exactArc = I.arcThroughEndpoints(arcPoints, {
    straightToleranceMm: 1.5,
    arcResidualRatio: 0.04,
    minimumArcSweepDeg: 20,
    maximumArcSweepDeg: 335,
});
assert.ok(exactArc, "A curved run should be recognized independently inside a future mixed stroke");
assert.equal(exactArc.type, "arc");
const reconstructedStart = G.pointAt(exactArc.center, exactArc.radiusMm, exactArc.startAngleDeg);
const reconstructedEnd = G.pointAt(exactArc.center, exactArc.radiusMm, exactArc.startAngleDeg + exactArc.sweepAngleDeg);
assert.ok(G.distance(reconstructedStart, arcPoints[0]) < 0.01, "Corrected arc must pass through the shared start junction");
assert.ok(G.distance(reconstructedEnd, arcPoints.at(-1)) < 0.01, "Corrected arc must pass through the shared end junction");

const irregular = [
    G.point(0, 0), G.point(12, 8), G.point(24, -5), G.point(36, 17), G.point(48, -12),
    G.point(60, 21), G.point(72, 2), G.point(84, 19), G.point(96, -4), G.point(108, 11),
];
const irregularResult = I.interpret(irregular, {
    closed: false,
    straightToleranceMm: 1,
    simplifyToleranceMm: 2,
    minimumSegmentMm: 28,
});
assert.notEqual(irregularResult.type, "line", "Intelligence must not force genuinely irregular mouse gestures into a straight primitive");

console.log("Door Drawing V3 smart stroke intelligence tests passed");
