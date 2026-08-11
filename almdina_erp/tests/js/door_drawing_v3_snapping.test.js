"use strict";

const assert = require("node:assert/strict");
const path = require("node:path");

global.window = {};
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/domain/geometry.js"));
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/domain/document.js"));
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/domain/smart_path_domain.js"));
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/application/snapping.js"));
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/application/smart_path_snapping.js"));

const V3 = global.window.AlmdinaDoorDrawingV3;
const G = V3.Geometry;
const D = V3.DocumentModel;
const S = V3.Snapping;

const line = G.line("L1", G.point(0, 0), G.point(100, 0));
const rectangle = G.rectangle("R1", G.point(200, 100), 80, 60);
const circle = G.circle("C1", G.point(400, 200), 50);
const arc = G.arc("A1", G.point(600, 200), 100, 0, 90);
const smartPath = G.path("P1", [G.point(700, 100), G.point(760, 100), G.point(760, 180)], false);
let document = D.create({ widthMm: 800, heightMm: 2100 });
for (const object of [line, rectangle, circle, arc, smartPath]) document = D.addObject(document, object);

const anchors = S.collectAnchors(document);
assert.ok(anchors.some(anchor => anchor.objectId === "L1" && anchor.role === "start"));
assert.ok(anchors.some(anchor => anchor.objectId === "L1" && anchor.role === "end"));
assert.ok(anchors.some(anchor => anchor.objectId === "R1" && anchor.role === "top-right" && anchor.point.x === 280 && anchor.point.y === 160));
assert.ok(anchors.some(anchor => anchor.objectId === "C1" && anchor.role === "east" && anchor.point.x === 450));
assert.ok(anchors.some(anchor => anchor.objectId === "A1" && anchor.role === "end" && anchor.point.x === 600 && anchor.point.y === 300));
assert.ok(anchors.some(anchor => anchor.objectId === "P1" && anchor.role === "node-1" && anchor.point.x === 760 && anchor.point.y === 100));
assert.equal(anchors.find(anchor => anchor.objectId === "P1" && anchor.role === "node-1").kind, "joint");
assert.ok(S.DEFAULT_SNAP_PX >= 20, "Default magnetic radius must be forgiving enough for normal mouse use");
assert.ok(S.JOIN_SNAP_PX > S.DEFAULT_SNAP_PX, "Join endpoints should have a slightly larger magnetic capture radius");
assert.ok(S.MOVE_JOIN_SNAP_PX >= 40, "Whole-object movement needs a larger capture radius than drawing a new segment");
assert.ok(S.MOVE_SNAP_RELEASE_FACTOR > 1, "A joined moving object should use hysteresis instead of immediately falling off the joint");

assert.equal(S.worldTolerance(2, 14), 7, "Snap radius must stay stable in screen pixels across zoom levels");

const endpointSnap = S.resolvePoint(document, G.point(106, 4), { viewportScale: 1, snapPx: 14 });
assert.equal(endpointSnap.snapped, true);
assert.deepEqual(endpointSnap.point, G.point(100, 0));
assert.equal(endpointSnap.target.objectId, "L1");
assert.equal(endpointSnap.target.role, "end");
assert.equal(endpointSnap.kind, "joint");

const pathNodeSnap = S.resolvePoint(document, G.point(749, 104), { viewportScale: 1, snapPx: 14 });
assert.equal(pathNodeSnap.snapped, true, "New geometry should magnetically find smart path nodes");
assert.deepEqual(pathNodeSnap.point, G.point(760, 100));
assert.equal(pathNodeSnap.target.objectId, "P1");
assert.equal(pathNodeSnap.target.role, "node-1");

const forgivingStart = S.resolvePoint(document, G.point(119, 0), { viewportScale: 1 });
assert.equal(forgivingStart.snapped, true, "A new segment started near an endpoint should connect without pixel-perfect aiming");
assert.deepEqual(forgivingStart.point, G.point(100, 0));

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

const offAxisDocument = D.addObject(D.create({ widthMm: 500, heightMm: 500 }), G.line("off", G.point(100, 5), G.point(160, 5)));
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

const forcedVerticalDocument = D.addObject(D.create({ widthMm: 500, heightMm: 500 }), G.line("vertical-target", G.point(50, 175), G.point(100, 175)));
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

const compatibleArcTargetDoc = D.addObject(D.create({ widthMm: 800, heightMm: 800 }), G.line("target", G.point(600, 300), G.point(650, 300)));
const exactArcSnap = S.resolveArcEndpoint(compatibleArcTargetDoc, G.point(603, 297), G.point(600, 200), 100, {
    viewportScale: 1,
    snapPx: 14,
});
assert.equal(exactArcSnap.snapped, true);
assert.deepEqual(exactArcSnap.point, G.point(600, 300));

let moveDocument = D.create({ widthMm: 500, heightMm: 500 });
const fixedHorizontal = G.line("fixed", G.point(0, 0), G.point(100, 0));
const movingVertical = G.line("moving", G.point(150, 0), G.point(150, 100));
moveDocument = D.addObject(moveDocument, fixedHorizontal);
moveDocument = D.addObject(moveDocument, movingVertical);
const moved = S.resolveObjectMove(moveDocument, movingVertical, -8, 0, { viewportScale: 1 });
assert.equal(moved.snapped, true, "Moving a whole piece should join even when its endpoint is still roughly 40px away");
assert.deepEqual(moved.object.geometry.start, G.point(100, 0));
assert.deepEqual(moved.object.geometry.end, G.point(100, 100));
assert.equal(G.lineLength(moved.object), 100, "Magnetic joining must translate the piece without changing its exact length");
assert.equal(moved.target.objectId, "fixed");
assert.equal(moved.target.role, "end");

let mixedMoveDocument = D.create({ widthMm: 1000, heightMm: 1000 });
const targetPath = G.path("target-path", [G.point(300, 0), G.point(360, 0)], false);
const movingLine = G.line("moving-line", G.point(340, 0), G.point(340, 80));
mixedMoveDocument = D.addObject(mixedMoveDocument, targetPath);
mixedMoveDocument = D.addObject(mixedMoveDocument, movingLine);
const lineToPath = S.resolveObjectMove(mixedMoveDocument, movingLine, 0, 0, { viewportScale: 1 });
assert.equal(lineToPath.snapped, true, "Whole-object movement must connect ordinary geometry to smart path nodes");
assert.deepEqual(lineToPath.object.geometry.start, G.point(360, 0));
assert.equal(lineToPath.target.objectId, "target-path");

const movingPath = G.path("moving-path", [G.point(450, 0), G.point(450, 100)], false);
let pathMoveDocument = D.create({ widthMm: 1000, heightMm: 1000 });
pathMoveDocument = D.addObject(pathMoveDocument, fixedHorizontal);
pathMoveDocument = D.addObject(pathMoveDocument, movingPath);
const pathToLine = S.resolveObjectMove(pathMoveDocument, movingPath, -310, 0, { viewportScale: 1 });
assert.equal(pathToLine.snapped, true, "Smart paths themselves must magnetically connect to ordinary endpoints when moved");
assert.deepEqual(pathToLine.object.geometry.points[0], G.point(100, 0));
assert.equal(G.pathLength(pathToLine.object), 100);

const stickyMove = S.resolveObjectMove(moveDocument, movingVertical, 20, 0, {
    viewportScale: 1,
    stickySource: moved.source,
    stickyTarget: moved.target,
});
assert.equal(stickyMove.snapped, true, "Once joined, normal hand jitter should not immediately detach the moved piece");
assert.equal(stickyMove.sticky, true);
assert.deepEqual(stickyMove.object.geometry.start, G.point(100, 0));
assert.equal(G.lineLength(stickyMove.object), 100);

const releasedMove = S.resolveObjectMove(moveDocument, movingVertical, 60, 0, {
    viewportScale: 1,
    stickySource: moved.source,
    stickyTarget: moved.target,
});
assert.equal(releasedMove.snapped, false, "Pulling clearly beyond the release radius should detach the piece again");

console.log("Door Drawing V3 snapping tests passed");