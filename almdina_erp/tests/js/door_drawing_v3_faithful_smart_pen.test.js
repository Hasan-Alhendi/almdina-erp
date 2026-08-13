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

const irregular = [
    G.point(0, 0), G.point(12, 3), G.point(25, 1), G.point(38, 16),
    G.point(52, 34), G.point(68, 47), G.point(83, 39), G.point(96, 18),
    G.point(112, 8), G.point(126, 24), G.point(139, 49), G.point(154, 57),
];
const preserved = I.interpret(irregular, {
    straightToleranceMm: 4,
    simplifyToleranceMm: 6,
    smoothingPasses: 3,
    pathSmoothingPasses: 2,
    orthogonalize: true,
});
assert.equal(preserved.type, "path");
assert.equal(preserved.fidelity, true);
assert.deepEqual(preserved.points, irregular, "Freehand must preserve every sampled point");

const roughL = [
    G.point(0, 0), G.point(18, 1.3), G.point(36, -0.8), G.point(55, 1.1), G.point(75, 0.5),
    G.point(77, 14), G.point(74.8, 30), G.point(76.2, 48), G.point(75, 66),
];
const lResult = I.interpret(roughL, { straightToleranceMm: 3, straightRatio: 1.08, simplifyToleranceMm: 5 });
assert.equal(lResult.type, "path");
assert.deepEqual(lResult.points, roughL, "A corner must not be rebuilt automatically");

const exactLine = [G.point(0, 0), G.point(20, 0), G.point(40, 0), G.point(70, 0), G.point(100, 0)];
const lineResult = I.interpret(exactLine, { straightToleranceMm: 3, straightRatio: 1.05 });
assert.equal(lineResult.type, "path", "Even a perfect hand-drawn line must remain a freehand path");
assert.deepEqual(lineResult.points, exactLine, "The pen must never replace the stroke with a native line automatically");

const almostLineButIntentionalCurve = [
    G.point(0, 0), G.point(20, 0.9), G.point(40, 2.4), G.point(60, 4.5), G.point(80, 7.1), G.point(100, 10.5),
];
const subtleCurve = I.interpret(almostLineButIntentionalCurve, { straightToleranceMm: 5, straightRatio: 1.08 });
assert.equal(subtleCurve.type, "path");
assert.deepEqual(subtleCurve.points, almostLineButIntentionalCurve);

const state = I.createStabilizer("mouse", G.point(0, 0));
const rawLivePoint = G.point(10, 0);
const stabilizedLivePoint = I.pushStabilized(state, rawLivePoint, { motionScaleMm: 20 });
assert.ok(stabilizedLivePoint.x > 0 && stabilizedLivePoint.x < rawLivePoint.x, "Preview stabilization must stay separate from committed geometry");

const closed = [G.point(0, 0), G.point(30, 5), G.point(38, 28), G.point(8, 36), G.point(0, 0)];
const closedResult = I.interpret(closed, { closed: true });
assert.equal(closedResult.type, "path");
assert.equal(closedResult.closed, true);
assert.deepEqual(closedResult.points, closed.slice(0, -1));

console.log("Door Drawing V3 faithful smart-pen tests passed");
