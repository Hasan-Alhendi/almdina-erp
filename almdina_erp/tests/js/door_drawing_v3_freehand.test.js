"use strict";

const assert = require("node:assert/strict");
const path = require("node:path");

global.window = {};
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/domain/geometry.js"));
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/domain/document.js"));
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/domain/smart_path_domain.js"));
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/application/smart_freehand_policy.js"));

const V3 = global.window.AlmdinaDoorDrawingV3;
const G = V3.Geometry;
const F = V3.SmartFreehandPolicy;

const noisyLine = [];
for (let x = 0; x <= 240; x += 8) noisyLine.push(G.point(x, x % 16 === 0 ? 0.55 : -0.45));
const line = F.recognize(noisyLine, { straightToleranceMm: 2, simplifyToleranceMm: 1 });
assert.equal(line.type, "line", "A hand-drawn nearly straight stroke should become an exact line");
assert.deepEqual(line.start, noisyLine[0]);
assert.deepEqual(line.end, noisyLine.at(-1));

const arcPoints = [];
for (let angle = 5; angle <= 125; angle += 5) {
    const radius = 90 + (angle % 10 === 0 ? 0.35 : -0.25);
    arcPoints.push(G.pointAt(G.point(100, 120), radius, angle));
}
const arc = F.recognize(arcPoints, { straightToleranceMm: 1.8, simplifyToleranceMm: 0.8 });
assert.equal(arc.type, "arc", "A smooth hand-drawn circular sweep should be corrected to a native arc");
assert.ok(Math.abs(arc.radiusMm - 90) < 1.5);
assert.ok(Math.abs(Math.abs(arc.sweepAngleDeg) - 120) < 5);

const circlePoints = [];
for (let angle = 0; angle <= 360; angle += 12) {
    const radius = 70 + (angle % 24 === 0 ? 0.3 : -0.2);
    circlePoints.push(G.pointAt(G.point(300, 250), radius, angle));
}
circlePoints[circlePoints.length - 1] = circlePoints[0];
const circle = F.recognize(circlePoints, { closed: true, straightToleranceMm: 1.8, simplifyToleranceMm: 0.8 });
assert.equal(circle.type, "circle", "A closed hand-drawn round stroke should become a native circle");
assert.ok(Math.abs(circle.radiusMm - 70) < 1.5);

const irregular = [
    G.point(0, 0), G.point(20, 3), G.point(40, 1), G.point(65, 30), G.point(78, 62),
    G.point(95, 78), G.point(118, 55), G.point(135, 20), G.point(160, 8), G.point(190, 42),
];
const cleaned = F.recognize(irregular, { straightToleranceMm: 1, simplifyToleranceMm: 4 });
assert.equal(cleaned.type, "path", "A genuinely free shape must remain a free editable path");
assert.ok(cleaned.points.length < irregular.length, "Smart cleanup should remove hand jitter/redundant samples");
assert.deepEqual(cleaned.points[0], irregular[0]);
assert.deepEqual(cleaned.points.at(-1), irregular.at(-1));

const sampled = F.appendSample([G.point(0, 0)], G.point(0.2, 0.1), 1);
assert.equal(sampled.length, 1, "Sub-pixel-equivalent jitter should not create a new geometry node");
const sampledFar = F.appendSample(sampled, G.point(2, 0), 1);
assert.equal(sampledFar.length, 2);

console.log("Door Drawing V3 intelligent freehand tests passed");
