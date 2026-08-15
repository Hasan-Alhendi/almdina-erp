"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const ROOT = path.resolve(__dirname, "../..");
global.window = {};
require(path.join(ROOT, "public/js/door_drawing_v3/domain/geometry.js"));
require(path.join(ROOT, "public/js/door_drawing_v3/domain/smart_stroke_reconstruction_domain.js"));
require(path.join(ROOT, "public/js/door_drawing_v3/application/adaptive_stroke_reconstructor.js"));

const V3 = global.window.AlmdinaDoorDrawingV3;
const G = V3.Geometry;
const Domain = V3.SmartStrokeReconstructionDomain;
const Reconstructor = V3.AdaptiveStrokeReconstructor;

function hasHandles(result) {
    return result.nodes.some(node => node && (node.in || node.out));
}

const wobblyStraight = [
    G.point(0, 0), G.point(10, 2.7), G.point(20, -2.4), G.point(30, 3.1),
    G.point(40, -2.8), G.point(50, 2.5), G.point(60, -3.0), G.point(70, 2.8),
    G.point(80, -2.4), G.point(90, 2.9), G.point(100, -2.6), G.point(110, 1.8), G.point(120, 0),
];
const straight = Reconstructor.reconstruct(wobblyStraight, "mouse");
assert.equal(straight.points.length, 2, "Alternating hand tremor around one heading must reconstruct as one exact line");
assert.equal(straight.straightSegmentCount, 1);
assert.equal(straight.curveSegmentCount, 0);
assert.equal(hasHandles(straight), false, "A straight freehand intent must not receive fake Bezier handles");
assert.deepEqual(straight.points[0], wobblyStraight[0]);
assert.deepEqual(straight.points[1], wobblyStraight[wobblyStraight.length - 1]);

const roughArch = [];
for (let index = 0; index <= 30; index += 1) {
    const x = index * 4;
    const y = 31 * Math.sin(Math.PI * x / 120);
    const jitter = index % 4 === 0 ? 1.8 : (index % 4 === 1 ? -1.2 : (index % 4 === 2 ? 0.8 : -0.5));
    roughArch.push(G.point(x, y + jitter));
}
roughArch[0] = G.point(0, 0);
roughArch[roughArch.length - 1] = G.point(120, 0);
const arch = Reconstructor.reconstruct(roughArch, "mouse");
assert.ok(arch.points.length >= 3, "An intentional arch must never collapse to a single straight segment");
assert.ok(arch.curveSegmentCount >= 1, "An intentional arch must be rebuilt as real Bezier geometry");
assert.ok(hasHandles(arch), "A reconstructed freehand curve must contain Bezier control handles");
assert.ok(Math.max(...arch.points.map(point => point.y)) > 20, "The large-scale arch silhouette must survive reconstruction");

const roughL = [
    G.point(0, 0), G.point(10, 1.5), G.point(20, -1.3), G.point(30, 1.7), G.point(40, -1.4),
    G.point(50, 1.2), G.point(60, 0),
    G.point(61.1, 10), G.point(58.7, 20), G.point(61.4, 30), G.point(58.9, 40),
    G.point(60.8, 50), G.point(60, 60),
];
const elbow = Reconstructor.reconstruct(roughL, "mouse");
assert.ok(elbow.cornerCount >= 1, "A deliberate L turn must be recognized as a protected corner");
assert.ok(elbow.points.length >= 3, "The corner must remain an explicit anchor");
assert.ok(elbow.straightSegmentCount >= 2, "Both noisy arms around an L corner should reconstruct as straight local spans");

const mixed = [];
for (let x = 0; x <= 50; x += 5) mixed.push(G.point(x, (x / 5) % 2 ? 1.1 : -0.9));
for (let x = 55; x <= 145; x += 5) {
    const t = (x - 55) / 90;
    mixed.push(G.point(x, 27 * Math.sin(Math.PI * t) + ((x / 5) % 2 ? 0.7 : -0.6)));
}
for (let x = 150; x <= 200; x += 5) mixed.push(G.point(x, (x / 5) % 2 ? 1.0 : -0.8));
mixed[0] = G.point(0, 0);
mixed[mixed.length - 1] = G.point(200, 0);
const mixedResult = Reconstructor.reconstruct(mixed, "mouse");
assert.ok(mixedResult.points.length > 2, "A line-curve-line gesture must never be classified as one global straight line");
assert.ok(mixedResult.curveSegmentCount >= 1, "The curved region of a mixed gesture must survive as Bezier geometry");
assert.ok(hasHandles(mixedResult));

const flower = [];
for (let index = 0; index <= 48; index += 1) {
    const angle = (Math.PI * 2 * index) / 48;
    const radius = 36 + 8 * Math.sin(5 * angle);
    flower.push(G.point(80 + radius * Math.cos(angle), 60 + radius * Math.sin(angle)));
}
const flowerResult = Reconstructor.reconstruct(flower, "mouse");
assert.ok(flowerResult.points.length > 4, "An irregular flower-like silhouette must stay an irregular multi-anchor path");
assert.ok(flowerResult.curveSegmentCount >= 1);
assert.ok(hasHandles(flowerResult));

const source = fs.readFileSync(path.join(ROOT, "public/js/door_drawing_v3/domain/smart_stroke_reconstruction_domain.js"), "utf8");
const app = fs.readFileSync(path.join(ROOT, "public/js/door_drawing_v3/application/non_destructive_smart_suggestions.js"), "utf8");
const bootstrap = fs.readFileSync(path.join(ROOT, "public/js/door_cutting_order_special_shape_ux.js"), "utf8");

assert.match(source, /resampleUniform/);
assert.match(source, /straightEvidence/);
assert.match(source, /buildCurveSpan/);
assert.match(source, /curveSegmentCount/);
assert.doesNotMatch(source, /G\.(?:circle|rectangle|arc)\s*\(/i, "The freehand reconstructor must not replace strokes with primitive shapes");
assert.doesNotMatch(source, /document\.|querySelector|frappe\./, "The reconstruction domain must remain pure and UI-independent");
assert.match(app, /Reconstructor\.reconstruct\(points, pointerType\)/);
assert.match(app, /reconstruction\.nodes/);
assert.match(app, /Smart reconstruct freehand stroke/);
assert.ok(bootstrap.indexOf("/domain/bezier_path_domain.js") < bootstrap.indexOf("/domain/smart_stroke_reconstruction_domain.js"));
assert.ok(bootstrap.indexOf("/domain/smart_stroke_reconstruction_domain.js") < bootstrap.indexOf("/application/adaptive_stroke_reconstructor.js"));
assert.ok(bootstrap.indexOf("/application/adaptive_stroke_reconstructor.js") < bootstrap.indexOf("/application/non_destructive_smart_suggestions.js"));

console.log("Door Drawing V3 local smart stroke reconstruction passed");
