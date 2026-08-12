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

const V3 = global.window.AlmdinaDoorDrawingV3;
const G = V3.Geometry;
const D = V3.DocumentModel;
const S = V3.Snapping;

assert.equal(S.EASY_MOVE_JOIN_SNAP_PX, 20, "Whole-object joining should capture only when pieces are genuinely close");

let document = D.create({ widthMm: 1000, heightMm: 1000 });
const baseline = G.line("baseline", G.point(0, 0), G.point(500, 0));
const referenceVertical = G.line("reference-vertical", G.point(400, 0), G.point(400, 220));
document = D.addObject(document, baseline);
document = D.addObject(document, referenceVertical);

const onEdge = S.resolvePoint(document, G.point(170, 8), { viewportScale: 1 });
assert.equal(onEdge.snapped, true, "A new line should be able to start on the body of an existing edge");
assert.deepEqual(onEdge.point, G.point(170, 0));
assert.equal(onEdge.kind, "surface");
assert.equal(onEdge.target.objectId, "baseline");
assert.equal(onEdge.smartGuide.type, "surface");

const sameTop = S.resolvePoint(document, G.point(175, 214), {
    anchor: G.point(170, 0),
    shiftKey: true,
    axisLock: true,
    viewportScale: 1,
});
assert.equal(sameTop.axis, "vertical");
assert.equal(sameTop.snapped, true, "A vertical line should align its endpoint to a remote parallel line endpoint");
assert.deepEqual(sameTop.point, G.point(170, 220));
assert.equal(sameTop.kind, "alignment");
assert.equal(sameTop.smartGuide.type, "horizontal-alignment");
assert.equal(sameTop.target.objectId, "reference-vertical");

let equalDoc = D.create({ widthMm: 1000, heightMm: 1000 });
const lengthReference = G.line("length-reference", G.point(500, 50), G.point(500, 250));
equalDoc = D.addObject(equalDoc, lengthReference);
const equalLength = S.resolvePoint(equalDoc, G.point(110, 221), {
    anchor: G.point(110, 30),
    shiftKey: true,
    axisLock: true,
    viewportScale: 1,
});
assert.equal(equalLength.snapped, true, "A nearly equal parallel line should snap to the exact reference length");
assert.deepEqual(equalLength.point, G.point(110, 230));
assert.equal(equalLength.kind, "equal-length");
assert.equal(equalLength.smartGuide.type, "equal-length");
assert.equal(equalLength.smartGuide.lengthMm, 200);

let moveDoc = D.create({ widthMm: 500, heightMm: 500 });
const fixed = G.line("fixed", G.point(0, 0), G.point(100, 0));
const nearMoving = G.line("moving", G.point(119, 0), G.point(119, 100));
moveDoc = D.addObject(moveDoc, fixed);
moveDoc = D.addObject(moveDoc, nearMoving);
const within20 = S.resolveObjectMove(moveDoc, nearMoving, 0, 0, { viewportScale: 1 });
assert.equal(within20.snapped, true, "19px should still magnetically join whole objects");
assert.deepEqual(within20.object.geometry.start, G.point(100, 0));

const farMoving = G.line("moving-far", G.point(121, 0), G.point(121, 100));
let farMoveDoc = D.create({ widthMm: 500, heightMm: 500 });
farMoveDoc = D.addObject(farMoveDoc, fixed);
farMoveDoc = D.addObject(farMoveDoc, farMoving);
const beyond20 = S.resolveObjectMove(farMoveDoc, farMoving, 0, 0, { viewportScale: 1 });
assert.equal(beyond20.snapped, false, "21px should no longer pull a whole object from visibly far away");

const source = require("node:fs").readFileSync(path.resolve(__dirname, "../../public/js/door_drawing_v3/application/smart_guides.js"), "utf8");
assert.doesNotMatch(source, /window\.document|document\.querySelector|document\.createElement|getBoundingClientRect|clientX|clientY/, "Smart-guide geometry policy must stay independent from browser DOM/event coordinates");

console.log("Door Drawing V3 smart guide tests passed");
