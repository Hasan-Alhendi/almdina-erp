"use strict";

const assert = require("node:assert/strict");
const path = require("node:path");

global.window = {};
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/domain/geometry.js"));
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/domain/document.js"));
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/domain/smart_path_domain.js"));
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/application/snapping.js"));
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/application/smart_path_snapping.js"));
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/application/move_snap_policy.js"));
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/application/smart_guides.js"));
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/application/unified_snap_engine.js"));

const V3 = global.window.AlmdinaDoorDrawingV3;
const G = V3.Geometry;
const D = V3.DocumentModel;
const S = V3.Snapping;

assert.equal(S.MOVE_JOIN_CAPTURE_PX, 20, "Whole-object magnetic join capture remains 20px");
assert.ok(S.INTENT_RANK.joint > S.INTENT_RANK.midpoint);
assert.ok(S.INTENT_RANK.midpoint > S.INTENT_RANK.surface);
assert.ok(S.INTENT_RANK.surface > S.INTENT_RANK.alignment);

// 1) After drawing, moving a vertical line can land its endpoint on the body
// of a lower line, not only on one of the lower line's endpoints.
let surfaceDoc = D.create({ widthMm: 1000, heightMm: 1000 });
const baseline = G.line("baseline", G.point(0, 0), G.point(500, 0));
const vertical = G.line("vertical", G.point(170, 100), G.point(170, 300));
surfaceDoc = D.addObject(surfaceDoc, baseline);
surfaceDoc = D.addObject(surfaceDoc, vertical);
const movedToSurface = S.resolveObjectMove(surfaceDoc, vertical, 0, -89, { viewportScale: 1 });
assert.equal(movedToSurface.snapped, true);
assert.equal(movedToSurface.kind, "surface");
assert.deepEqual(movedToSurface.object.geometry.start, G.point(170, 0));
assert.deepEqual(movedToSurface.object.geometry.end, G.point(170, 200));
assert.equal(movedToSurface.smartGuide.type, "surface");

// 2) Remote alignment works while moving an already-created object. The
// geometry is corrected, not only the guide rendered on screen.
let alignDoc = D.create({ widthMm: 1000, heightMm: 1000 });
const reference = G.line("reference", G.point(400, 0), G.point(400, 200));
const moving = G.line("moving", G.point(100, 20), G.point(100, 220));
alignDoc = D.addObject(alignDoc, reference);
alignDoc = D.addObject(alignDoc, moving);
const alignedMove = S.resolveObjectMove(alignDoc, moving, 0, -17, { viewportScale: 1 });
assert.equal(alignedMove.snapped, true);
assert.equal(alignedMove.kind, "alignment");
assert.equal(alignedMove.object.geometry.end.y, 200);
assert.equal(alignedMove.object.geometry.start.y, 0);
assert.equal(alignedMove.smartGuide.type, "horizontal-alignment");

// 3) Midpoint is a stronger intent than merely landing somewhere on an edge.
let midpointDoc = D.create({ widthMm: 500, heightMm: 500 });
const horizontal = G.line("horizontal", G.point(0, 0), G.point(200, 0));
const shortVertical = G.line("short", G.point(108, 5), G.point(108, 55));
midpointDoc = D.addObject(midpointDoc, horizontal);
midpointDoc = D.addObject(midpointDoc, shortVertical);
const midpointSnap = S.resolveObjectMove(midpointDoc, shortVertical, 0, 0, { viewportScale: 1 });
assert.equal(midpointSnap.snapped, true);
assert.equal(midpointSnap.kind, "midpoint");
assert.deepEqual(midpointSnap.object.geometry.start, G.point(100, 0));
assert.equal(midpointSnap.smartGuide.type, "midpoint");

// 4) Endpoint editing uses the same engine. Supplying an opposite endpoint as
// an anchor must not disable snapping to the body of another segment.
let handleDoc = D.create({ widthMm: 500, heightMm: 500 });
const lower = G.line("lower", G.point(0, 0), G.point(300, 0));
const edited = G.line("edited", G.point(130, 100), G.point(130, 200));
handleDoc = D.addObject(handleDoc, lower);
handleDoc = D.addObject(handleDoc, edited);
const handleSurface = S.resolvePoint(handleDoc, G.point(131, 7), {
    anchor: edited.geometry.end,
    viewportScale: 1,
    excludeId: edited.id,
});
assert.equal(handleSurface.snapped, true);
assert.equal(handleSurface.kind, "surface");
assert.deepEqual(handleSurface.point, G.point(131, 0));

// 5) Hysteresis keeps a deliberate connection stable beyond the capture
// radius, but only for the same geometric intent.
const firstSurface = S.resolveObjectMove(surfaceDoc, vertical, 0, -89, { viewportScale: 1 });
const stickySurface = S.resolveObjectMove(surfaceDoc, vertical, 0, -84, {
    viewportScale: 1,
    stickySource: firstSurface.source,
    stickyTarget: firstSurface.target,
    stickyKind: firstSurface.kind,
});
assert.equal(stickySurface.snapped, true);
assert.equal(stickySurface.kind, "surface");
assert.equal(stickySurface.sticky, true);
assert.equal(stickySurface.object.geometry.start.y, 0);

console.log("Door Drawing V3 unified snap engine tests passed");
