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
assert.equal(preserved.type, "path", "An irregular freehand gesture must remain a path");
assert.equal(preserved.fidelity, true, "Fallback freehand geometry must be explicitly fidelity-preserving");
assert.deepEqual(preserved.points, irregular, "Freehand fallback must preserve every sampled point instead of smoothing or simplifying the silhouette");

const roughL = [
    G.point(0, 0), G.point(18, 1.3), G.point(36, -0.8), G.point(55, 1.1), G.point(75, 0.5),
    G.point(77, 14), G.point(74.8, 30), G.point(76.2, 48), G.point(75, 66),
];
const lResult = I.interpret(roughL, {
    straightToleranceMm: 3,
    straightRatio: 1.08,
    simplifyToleranceMm: 5,
    minimumSegmentMm: 12,
});
assert.equal(lResult.type, "path", "A multi-direction freehand stroke must not be auto-split into compound straight segments");
assert.deepEqual(lResult.points, roughL, "Corner recognition must never rebuild a freehand stroke automatically");

const exactLine = [G.point(0, 0), G.point(20, 0), G.point(40, 0), G.point(70, 0), G.point(100, 0)];
const lineResult = I.interpret(exactLine, { straightToleranceMm: 3, straightRatio: 1.05 });
assert.equal(lineResult.type, "line", "An unmistakably straight gesture should still receive useful smart recognition");
assert.deepEqual(lineResult.start, exactLine[0]);
assert.deepEqual(lineResult.end, exactLine.at(-1));

const almostLineButIntentionalCurve = [
    G.point(0, 0), G.point(20, 0.9), G.point(40, 2.4), G.point(60, 4.5), G.point(80, 7.1), G.point(100, 10.5),
];
const subtleCurve = I.interpret(almostLineButIntentionalCurve, { straightToleranceMm: 5, straightRatio: 1.08 });
assert.equal(subtleCurve.type, "path", "A subtle intentional curve must not be flattened merely because it is near a line");
assert.deepEqual(subtleCurve.points, almostLineButIntentionalCurve);

const state = I.createStabilizer("mouse", G.point(0, 0));
const livePoint = G.point(31.25, 17.75);
assert.deepEqual(I.pushStabilized(state, livePoint), livePoint, "Live preview must follow the actual sampled point without lagging deformation");
assert.deepEqual(state.point, livePoint);

const closed = [G.point(0, 0), G.point(30, 5), G.point(38, 28), G.point(8, 36), G.point(0, 0)];
const closedResult = I.interpret(closed, { closed: true, circleResidualRatio: 0.001, simplifyToleranceMm: 10 });
assert.equal(closedResult.type, "path");
assert.equal(closedResult.closed, true);
assert.deepEqual(closedResult.points, closed.slice(0, -1), "Closed freehand geometry should preserve the stroke and only remove the redundant closing duplicate");

console.log("Door Drawing V3 faithful smart-pen tests passed");
