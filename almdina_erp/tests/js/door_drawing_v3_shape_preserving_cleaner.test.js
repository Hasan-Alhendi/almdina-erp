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

function clone(points) { return points.map(point => G.point(point.x, point.y)); }
function hasPoint(points, expected, tolerance = 0.01) {
    return points.some(point => G.distance(point, expected) <= tolerance);
}
function maxAbsY(points) { return Math.max(...points.map(point => Math.abs(point.y))); }

const visiblyWobblyLine = [
    G.point(0, 0), G.point(10, 2.4), G.point(20, -2.1), G.point(30, 3.0),
    G.point(40, -2.7), G.point(50, 2.2), G.point(60, -2.9), G.point(70, 2.6),
    G.point(80, -2.2), G.point(90, 2.8), G.point(100, -2.5), G.point(110, 1.9),
    G.point(120, 0),
];
const wobblySnapshot = clone(visiblyWobblyLine);
const straight = Cleaner.clean(visiblyWobblyLine, "mouse");
assert.equal(straight.straightenedRuns.length, 1, "Visible hand tremor around one direction must still be understood as a straight intent");
assert.equal(straight.points.length, 2, "A recognized straight intent must become one exact segment inside the same Path");
assert.deepEqual(straight.points[0], visiblyWobblyLine[0]);
assert.deepEqual(straight.points[1], visiblyWobblyLine[visiblyWobblyLine.length - 1]);
assert.ok(straight.maximumDeviationMm >= 2, "The regression must prove that correction is no longer limited to sub-millimetre noise");
assert.deepEqual(visiblyWobblyLine, wobblySnapshot, "Smart cleanup must never mutate sampled source points");

const horizontalQuality = Domain.straightQuality(visiblyWobblyLine, Cleaner.PROFILES.mouse);
assert.equal(horizontalQuality.eligible, true);
assert.ok(horizontalQuality.curveBias < Cleaner.PROFILES.mouse.curveBiasThreshold, "Alternating jitter should look like tremor, not a deliberate curve");

const roughL = [
    G.point(0, 0), G.point(10, 1.8), G.point(20, -1.7), G.point(30, 2.0),
    G.point(40, -1.9), G.point(50, 1.7), G.point(60, -1.8), G.point(70, 1.4),
    G.point(80, 0),
    G.point(81.5, 10), G.point(78.3, 20), G.point(82.0, 30), G.point(78.4, 40),
    G.point(81.7, 50), G.point(78.6, 60), G.point(81.2, 70), G.point(80, 80),
];
const lResult = Cleaner.clean(roughL, "mouse");
assert.ok(lResult.cornerIndices.length >= 1, "The deliberate L corner must survive trend filtering");
assert.ok(lResult.straightenedRuns.length >= 2, "Both visibly noisy L arms must become straight intent runs");
const protectedCorner = roughL[lResult.cornerIndices[0]];
assert.ok(hasPoint(lResult.points, protectedCorner), "A protected direction-change anchor must remain exact");
assert.ok(lResult.points.length <= 5, "High-frequency hand noise should disappear instead of remaining as many small segments");

const intentionalShallowCurve = [];
for (let x = 0; x <= 120; x += 10) {
    const base = 5.2 * Math.sin(Math.PI * x / 120);
    const handNoise = (x / 10) % 2 === 0 ? 0.35 : -0.3;
    intentionalShallowCurve.push(G.point(x, base + handNoise));
}
intentionalShallowCurve[0] = G.point(0, 0);
intentionalShallowCurve[intentionalShallowCurve.length - 1] = G.point(120, 0);
const shallowQuality = Domain.straightQuality(intentionalShallowCurve, Cleaner.PROFILES.mouse);
assert.equal(shallowQuality.deliberateCurve, true, "One-sided bow is evidence of a real curve, not hand tremor");
const shallow = Cleaner.clean(intentionalShallowCurve, "mouse");
assert.equal(shallow.straightenedRuns.length, 0, "A deliberate shallow curve must never be flattened just because it is close to a line");
assert.ok(shallow.points.length > 2);
assert.ok(maxAbsY(shallow.points) > 3.5, "The curve silhouette must remain visibly curved after cleanup");

const roughArch = [];
for (let index = 0; index <= 24; index += 1) {
    const x = index * 5;
    const arch = 28 * Math.sin(Math.PI * x / 120);
    const jitter = index % 3 === 0 ? 1.8 : (index % 3 === 1 ? -1.4 : 0.9);
    roughArch.push(G.point(x, arch + jitter));
}
roughArch[0] = G.point(0, 0);
roughArch[roughArch.length - 1] = G.point(120, 0);
const arch = Cleaner.clean(roughArch, "mouse");
assert.equal(arch.straightenedRuns.length, 0);
assert.ok(arch.points.length >= 4, "An arch must remain a multi-point path");
assert.ok(maxAbsY(arch.points) > 22, "Cleanup must retain the large-scale arch silhouette");
assert.ok(arch.points.length < roughArch.length, "Visible micro-zigzags should be simplified out of a free curve");
assert.deepEqual(arch.points[0], roughArch[0]);
assert.deepEqual(arch.points[arch.points.length - 1], roughArch[roughArch.length - 1]);

const penProfile = Cleaner.profile("pen");
const mouseProfile = Cleaner.profile("mouse");
assert.ok(penProfile.maxCurveDisplacementMm < mouseProfile.maxCurveDisplacementMm, "Stylus cleanup stays gentler than mouse cleanup");
assert.ok(penProfile.straightMaximumDeviationMm < mouseProfile.straightMaximumDeviationMm);
assert.equal(Cleaner.profile("unknown"), Cleaner.PROFILES.mouse);

const bootstrap = fs.readFileSync(path.join(ROOT, "public/js/door_cutting_order_special_shape_ux.js"), "utf8");
const application = fs.readFileSync(path.join(ROOT, "public/js/door_drawing_v3/application/non_destructive_smart_suggestions.js"), "utf8");
const domainSource = fs.readFileSync(path.join(ROOT, "public/js/door_drawing_v3/domain/shape_preserving_stroke_domain.js"), "utf8");

assert.ok(
    bootstrap.indexOf("/domain/shape_preserving_stroke_domain.js") < bootstrap.indexOf("/application/adaptive_stroke_cleaner.js"),
    "Pure stroke geometry must load before the adaptive profile"
);
assert.ok(
    bootstrap.indexOf("/application/adaptive_stroke_cleaner.js") < bootstrap.indexOf("/application/non_destructive_smart_suggestions.js"),
    "The cleaner must load before the active freehand owner"
);
assert.match(bootstrap, /__doorDrawingV3ShapePreservingCleaner:\s*true/);
assert.match(bootstrap, /__doorDrawingV3LocalStraightening:\s*true/);
assert.match(bootstrap, /__doorDrawingV3SmartCleanUndo:\s*true/);

assert.match(application, /Cleaner\.clean\(points, pointerType\)/);
assert.match(application, /c\.history\.execute\(rawDocument, "Draw freehand stroke"\)/);
assert.match(application, /"Smart clean freehand stroke"/);
assert.match(application, /G\.path\(rawObject\.id, cleaning\.points, false/);
assert.doesNotMatch(application, /const result = I\.interpret\(points, options\)/, "Committed freehand must never use primitive or compound recognition");

assert.match(domainSource, /trendSeries/);
assert.match(domainSource, /signedDistanceToLine/);
assert.match(domainSource, /curveBiasThreshold/);
assert.match(domainSource, /deliberateCurve/);
assert.match(domainSource, /Smooth each intent span independently/i);
assert.doesNotMatch(domainSource, /G\.(?:circle|rectangle|arc)\s*\(/i, "Automatic cleaner must not construct primitive geometry");
assert.doesNotMatch(domainSource, /document\.|querySelector|frappe\./, "Pure stroke domain must remain DOM and Frappe independent");

console.log("Door Drawing V3 intent-aware smart cleaner passed");
