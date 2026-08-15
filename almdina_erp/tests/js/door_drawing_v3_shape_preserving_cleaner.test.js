"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const ROOT = path.resolve(__dirname, "../..");
global.window = {};
require(path.join(ROOT, "public/js/door_drawing_v3/domain/geometry.js"));
require(path.join(ROOT, "public/js/door_drawing_v3/domain/shape_preserving_stroke_domain.js"));
require(path.join(ROOT, "public/js/door_drawing_v3/application/adaptive_stroke_cleaner.js"));

const V3 = global.window.AlmdinaDoorDrawingV3;
const G = V3.Geometry;
const Domain = V3.ShapePreservingStrokeDomain;
const Cleaner = V3.AdaptiveStrokeCleaner;

function clone(points) {
    return points.map(point => G.point(point.x, point.y));
}

function hasPoint(points, expected, tolerance = 0.01) {
    return points.some(point => G.distance(point, expected) <= tolerance);
}

const wobblyLine = [
    G.point(0, 0),
    G.point(25, 0.55),
    G.point(50, -0.62),
    G.point(75, 0.61),
    G.point(100, -0.48),
    G.point(125, 0.2),
];
const wobblySnapshot = clone(wobblyLine);
const straight = Cleaner.clean(wobblyLine, "mouse");
assert.equal(straight.straightenedRuns.length, 1, "A clearly wobbly straight stroke should be locally straightened");
assert.equal(straight.points.length, 2, "A single straight run should become an exact segment inside the same Path");
assert.deepEqual(straight.points[0], wobblyLine[0]);
assert.deepEqual(straight.points[1], wobblyLine[wobblyLine.length - 1]);
assert.ok(straight.maximumDeviationMm <= Cleaner.PROFILES.mouse.straightMaximumDeviationMm + 1e-6);
assert.deepEqual(wobblyLine, wobblySnapshot, "Smart cleanup must never mutate the sampled source stroke");

const roughL = [
    G.point(0, 0),
    G.point(20, 0.45),
    G.point(40, -0.35),
    G.point(60, 0.38),
    G.point(80, 0.1),
    G.point(80.45, 20),
    G.point(79.62, 40),
    G.point(80.36, 60),
    G.point(80.05, 80),
];
const lResult = Cleaner.clean(roughL, "mouse");
assert.ok(lResult.cornerIndices.length >= 1, "A real L corner must be detected and protected");
assert.ok(lResult.straightenedRuns.length >= 2, "Both noisy L arms should become straight runs");
const protectedCorner = roughL[lResult.cornerIndices[0]];
assert.ok(hasPoint(lResult.points, protectedCorner), "The user's sharp corner must survive cleanup exactly");
assert.ok(lResult.points.length <= 4, "Noise points should disappear while the L topology stays simple");

const intentionalCurve = [
    G.point(0, 0),
    G.point(20, 0.9),
    G.point(40, 2.4),
    G.point(60, 4.5),
    G.point(80, 7.1),
    G.point(100, 10.5),
];
const curve = Cleaner.clean(intentionalCurve, "mouse");
assert.equal(curve.straightenedRuns.length, 0, "A deliberate shallow curve must never be flattened into a line");
assert.ok(curve.points.length > 2, "The curve must remain a curve-like polyline rather than becoming one segment");
assert.deepEqual(curve.points[0], intentionalCurve[0]);
assert.deepEqual(curve.points[curve.points.length - 1], intentionalCurve[intentionalCurve.length - 1]);
assert.ok(
    curve.maximumDeviationMm <= Cleaner.PROFILES.mouse.maxCurveDisplacementMm + Cleaner.PROFILES.mouse.simplifyToleranceMm + 1e-6,
    "Curve cleanup must remain inside the strict shape-preserving displacement envelope"
);

const irregular = [
    G.point(0, 0), G.point(12, 4), G.point(25, 1), G.point(38, 18),
    G.point(52, 35), G.point(68, 49), G.point(83, 38), G.point(96, 17),
    G.point(112, 7), G.point(126, 25), G.point(139, 51), G.point(154, 58),
];
const irregularResult = Cleaner.clean(irregular, "mouse");
assert.ok(irregularResult.points.length >= 4, "An irregular silhouette must remain an irregular path, not collapse into a primitive");
assert.ok(irregularResult.maximumDeviationMm <= Cleaner.PROFILES.mouse.overallMaximumDeviationMm + 1e-6);
assert.deepEqual(irregularResult.points[0], irregular[0]);
assert.deepEqual(irregularResult.points[irregularResult.points.length - 1], irregular[irregular.length - 1]);

const penProfile = Cleaner.profile("pen");
const mouseProfile = Cleaner.profile("mouse");
assert.ok(penProfile.maxCurveDisplacementMm < mouseProfile.maxCurveDisplacementMm, "A stylus should receive gentler cleanup than a mouse");
assert.ok(penProfile.straightMaximumDeviationMm < mouseProfile.straightMaximumDeviationMm);
assert.equal(Cleaner.profile("unknown"), Cleaner.PROFILES.mouse);

const bootstrap = fs.readFileSync(path.join(ROOT, "public/js/door_cutting_order_special_shape_ux.js"), "utf8");
const application = fs.readFileSync(path.join(ROOT, "public/js/door_drawing_v3/application/non_destructive_smart_suggestions.js"), "utf8");
const domainSource = fs.readFileSync(path.join(ROOT, "public/js/door_drawing_v3/domain/shape_preserving_stroke_domain.js"), "utf8");

assert.ok(
    bootstrap.indexOf("/domain/shape_preserving_stroke_domain.js") < bootstrap.indexOf("/application/adaptive_stroke_cleaner.js"),
    "Pure stroke geometry must load before the adaptive application profile"
);
assert.ok(
    bootstrap.indexOf("/application/adaptive_stroke_cleaner.js") < bootstrap.indexOf("/application/non_destructive_smart_suggestions.js"),
    "The cleaner must be ready before the active freehand owner"
);
assert.match(bootstrap, /__doorDrawingV3ShapePreservingCleaner:\s*true/);
assert.match(bootstrap, /__doorDrawingV3LocalStraightening:\s*true/);
assert.match(bootstrap, /__doorDrawingV3SmartCleanUndo:\s*true/);

assert.match(application, /Cleaner\.clean\(points, pointerType\)/);
assert.match(application, /c\.history\.execute\(rawDocument, "Draw freehand stroke"\)/);
assert.match(application, /"Smart clean freehand stroke"/);
assert.match(application, /G\.path\(rawObject\.id, cleaning\.points, false/);
assert.doesNotMatch(application, /const result = I\.interpret\(points, options\)/, "Committed freehand must not use primitive or compound recognition");
assert.match(application, /Primitive recognition remains an optional suggestion layer/);

assert.match(domainSource, /maxCurveDisplacementMm:\s*0\.8/);
assert.match(domainSource, /straightMaximumDeviationMm:\s*1\.8/);
assert.match(domainSource, /detectCorners/);
assert.match(domainSource, /smoothBounded/);
assert.match(domainSource, /adaptiveStraightLimit/);
assert.match(domainSource, /maxSourceDeviation/);
assert.doesNotMatch(domainSource, /circle|rectangle|arc/i, "Shape-preserving cleaner must not recognize or construct primitive shape types");
assert.doesNotMatch(domainSource, /document\.|querySelector|frappe\./, "Pure stroke domain must remain DOM and Frappe independent");

console.log("Door Drawing V3 shape-preserving smart cleaner passed");
