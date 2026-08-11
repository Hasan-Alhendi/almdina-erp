"use strict";

const assert = require("node:assert/strict");
const path = require("node:path");

global.window = {};
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/domain/geometry.js"));
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/domain/document.js"));
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/application/snapping.js"));

const V3 = global.window.AlmdinaDoorDrawingV3;
const G = V3.Geometry;
const D = V3.DocumentModel;
const S = V3.Snapping;

const line = G.line("L1", G.point(0, 0), G.point(100, 0));
const rectangle = G.rectangle("R1", G.point(200, 100), 80, 60);
const circle = G.circle("C1", G.point(400, 200), 50);
const arc = G.arc("A1", G.point(600, 200), 100, 0, 90);
let document = D.create({ widthMm: 800, heightMm: 2100 });
for (const object of [line, rectangle, circle, arc]) document = D.addObject(document, object);

const anchors = S.collectAnchors(document);
assert.ok(anchors.some(anchor => anchor.objectId === "L1" && anchor.role === "start"));
assert.ok(anchors.some(anchor => anchor.objectId === "L1" && anchor.role === "end"));
assert.ok(anchors.some(anchor => anchor.objectId === "R1" && anchor.role === "top-right" && anchor.point.x === 280 && anchor.point.y === 160));
assert.ok(anchors.some(anchor => anchor.objectId === "C1" && anchor.role === "east" && anchor.point.x === 450));
assert.ok(anchors.some(anchor => anchor.objectId === "A1" && anchor.role === "end" && anchor.point.x === 600 && anchor.point.y === 300));

assert.equal(S.worldTolerance(2, 14), 7, "Snap radius must stay stable in screen pixels across zoom levels");

const endpointSnap = S.resolvePoint(document, G.point(106, 4), { viewportScale: 1, snapPx: 14 });
assert.equal(endpointSnap.snapped, true);
assert.deepEqual(endpointSnap.point, G.point(100, 0));
assert.equal(endpointSnap.target.objectId, "L1");
assert.equal(endpointSnap.target.role, "end");

const excluded = S.resolvePoint(document, G.point(106, 4), { viewportScale: 1, snapPx: 14, excludeId: "L1" });
assert.equal(excluded.snapped, false, "Endpoint editing must be able to exclude the selected object from snap targets");

const strictHorizontal = S.resolvePoint(document, G.point(97, 8), {
    anchor: G.point(0, 0),
    shiftKey: true,
    axisLock: true,
    viewportScale: 1,
    snapPx: 14,
});
assert.equal(strictHorizontal.axis, "horizontal");
assert.equal(strictHorizontal.snapped, true);
assert.deepEqual(strictHorizontal.point, G.point(100, 0), "Shift must remain strictly horizontal while snapping to a compatible endpoint");

const offAxisDocument = D.addObject(
    D.create({ widthMm: 500, heightMm: 500 }),
    G.line("off", G.point(100, 5), G.point(160, 5))
);
const strictNoBreak = S.resolvePoint(offAxisDocument, G.point(99, 6), {
    anchor: G.point(0, 0),
    shiftKey: true,
    axisLock: true,
    viewportScale: 1,
    snapPx: 14,
});
assert.equal(strictNoBreak.axis, "horizontal");
assert.equal(strictNoBreak.snapped, false, "A nearby target must never break the strict Shift axis constraint");
assert.equal(strictNoBreak.point.y, 0);

const forcedVerticalDocument = D.addObject(
    D.create({ widthMm: 500, heightMm: 500 }),
    G.line("vertical-target", G.point(50, 175), G.point(100, 175))
);
const forcedVertical = S.resolvePoint(forcedVerticalDocument, G.point(56, 171), {
    anchor: G.point(50, 50),
    forcedAxis: "vertical",
    viewportScale: 1,
    snapPx: 14,
});
assert.equal(forcedVertical.axis, "vertical");
assert.equal(forcedVertical.snapped, true, "Shape radius handles may force an axis without requiring Shift");
assert.deepEqual(forcedVertical.point, G.point(50, 175));

const arcEndpoint = S.resolveArcEndpoint(document, G.point(600.5, 299.5), G.point(600, 200), 100, {
    viewportScale: 1,
    snapPx: 14,
    excludeId: "A1",
});
assert.equal(arcEndpoint.snapped, false, "An arc endpoint only snaps to targets that lie on its exact radius");
assert.equal(G.roundMm(G.distance(G.point(600, 200), arcEndpoint.point)), 100);

const compatibleArcTargetDoc = D.addObject(
    D.create({ widthMm: 800, heightMm: 800 }),
    G.line("target", G.point(600, 300), G.point(650, 300))
);
const exactArcSnap = S.resolveArcEndpoint(compatibleArcTargetDoc, G.point(603, 297), G.point(600, 200), 100, {
    viewportScale: 1,
    snapPx: 14,
});
assert.equal(exactArcSnap.snapped, true);
assert.deepEqual(exactArcSnap.point, G.point(600, 300));

console.log("Door Drawing V3 snapping tests passed");
