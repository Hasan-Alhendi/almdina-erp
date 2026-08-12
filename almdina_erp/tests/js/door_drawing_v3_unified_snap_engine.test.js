"use strict";

const assert = require("node:assert/strict");
const path = require("node:path");

global.window = {};
for (const file of [
    "domain/geometry.js",
    "domain/document.js",
    "domain/smart_path_domain.js",
    "application/snapping.js",
    "application/smart_path_snapping.js",
    "application/move_snap_policy.js",
    "application/smart_guides.js",
    "application/unified_snap_engine.js",
]) require(path.resolve(__dirname, `../../public/js/door_drawing_v3/${file}`));

const V3 = global.window.AlmdinaDoorDrawingV3;
const G = V3.Geometry;
const D = V3.DocumentModel;
const S = V3.Snapping;

assert.equal(S.MOVE_CAPTURE_PX, 20, "Post-draw whole-object capture stays deliberately tight");
assert.ok(S.INTENT_PRIORITY.joint > S.INTENT_PRIORITY.surface);
assert.ok(S.INTENT_PRIORITY.surface > S.INTENT_PRIORITY.alignment);

// 1) A completed vertical line can be moved onto the body of a lower line.
let doc = D.create({ widthMm: 1000, heightMm: 1000 });
const baseline = G.line("baseline", G.point(0, 0), G.point(500, 0));
const moving = G.line("moving", G.point(180, 9), G.point(180, 209));
doc = D.addObject(doc, baseline);
doc = D.addObject(doc, moving);
let moved = S.resolveObjectMove(doc, moving, 0, 0, { viewportScale: 1 });
assert.equal(moved.snapped, true, "Completed line should snap to the body of another line while moving");
assert.equal(moved.kind, "surface");
assert.deepEqual(moved.object.geometry.start, G.point(180, 0));
assert.deepEqual(moved.object.geometry.end, G.point(180, 200));
assert.equal(G.lineLength(moved.object), 200, "Whole-object snapping must never resize the line");

// 2) Remote post-draw alignment should work even when the parallel line is far away in X.
let alignDoc = D.create({ widthMm: 1000, heightMm: 1000 });
const reference = G.line("reference", G.point(500, 50), G.point(500, 250));
const toAlign = G.line("to-align", G.point(100, 47), G.point(100, 247));
alignDoc = D.addObject(alignDoc, reference);
alignDoc = D.addObject(alignDoc, toAlign);
const aligned = S.resolveObjectMove(alignDoc, toAlign, 0, 0, { viewportScale: 1 });
assert.equal(aligned.snapped, true, "Completed parallel lines should align after drawing, not only during drawing");
assert.equal(aligned.kind, "alignment");
assert.deepEqual(aligned.object.geometry.start, G.point(100, 50));
assert.deepEqual(aligned.object.geometry.end, G.point(100, 250));
assert.equal(aligned.smartGuide.type, "horizontal-alignment");

// 3) Midpoints are first-class snap targets for drawing and endpoint editing.
const midpoint = S.resolvePoint(alignDoc, G.point(500, 151), { viewportScale: 1, excludeId: "to-align" });
assert.equal(midpoint.snapped, true);
assert.equal(midpoint.kind, "midpoint");
assert.deepEqual(midpoint.point, G.point(500, 150));

// 4) Intersections are computed even when no stored node exists there.
let intersectionDoc = D.create({ widthMm: 1000, heightMm: 1000 });
intersectionDoc = D.addObject(intersectionDoc, G.line("h", G.point(0, 100), G.point(300, 100)));
intersectionDoc = D.addObject(intersectionDoc, G.line("v", G.point(150, 0), G.point(150, 300)));
const intersection = S.resolvePoint(intersectionDoc, G.point(153, 104), { viewportScale: 1 });
assert.equal(intersection.snapped, true);
assert.equal(intersection.kind, "intersection");
assert.deepEqual(intersection.point, G.point(150, 100));
assert.equal(intersection.smartGuide.type, "intersection");

// 5) Endpoint editing can acquire a true perpendicular foot on an existing edge.
// Use x=230 so the perpendicular foot is not also the line midpoint; midpoint is
// intentionally a higher-priority intent and must not make this test ambiguous.
let perpendicularDoc = D.create({ widthMm: 1000, heightMm: 1000 });
perpendicularDoc = D.addObject(perpendicularDoc, G.line("target", G.point(0, 0), G.point(400, 0)));
const perpendicular = S.resolvePoint(perpendicularDoc, G.point(231, 4), {
    anchor: G.point(230, 200),
    viewportScale: 1,
});
assert.equal(perpendicular.snapped, true);
assert.equal(perpendicular.kind, "perpendicular");
assert.deepEqual(perpendicular.point, G.point(230, 0));
assert.equal(perpendicular.smartGuide.symbol, "⊥");

// 6) Parallel intent changes the angle, not the requested length.
let parallelDoc = D.create({ widthMm: 1000, heightMm: 1000 });
parallelDoc = D.addObject(parallelDoc, G.line("angle-ref", G.point(500, 500), G.point(700, 600)));
const anchor = G.point(50, 50);
const nearParallel = G.pointAt(anchor, 300, G.angleDeg(G.point(500, 500), G.point(700, 600)) + 1);
const parallel = S.resolvePoint(parallelDoc, nearParallel, { anchor, viewportScale: 1 });
assert.equal(parallel.snapped, true);
assert.equal(parallel.kind, "parallel");
assert.ok(Math.abs(G.distance(anchor, parallel.point) - 300) <= 0.001, "Parallel snap preserves requested segment length");
assert.ok(S.ANGLE_TOLERANCE_DEG <= 2);

// 7) Pure geometry policy: no browser pointer/DOM dependency inside the unified engine.
const fs = require("node:fs");
const source = fs.readFileSync(path.resolve(__dirname, "../../public/js/door_drawing_v3/application/unified_snap_engine.js"), "utf8");
assert.doesNotMatch(source, /querySelector|getBoundingClientRect|clientX|clientY|pointerId|document\./, "Unified snap policy must remain world-mm geometry, independent from browser coordinates");

console.log("Door Drawing V3 unified post-draw snap engine tests passed");
