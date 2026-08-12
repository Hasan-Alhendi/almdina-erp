"use strict";

const assert = require("node:assert/strict");
const path = require("node:path");

global.window = {};
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/domain/geometry.js"));
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/domain/document.js"));
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/domain/smart_path_domain.js"));
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/application/history.js"));
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/infrastructure/persistence_adapter.js"));
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/infrastructure/smart_path_persistence.js"));

const V3 = global.window.AlmdinaDoorDrawingV3;
const G = V3.Geometry;
const D = V3.DocumentModel;
const P = V3.PersistenceAdapter;

const line = G.line("L1", G.point(0, 0), G.point(214, 0));
assert.equal(G.lineLength(line), 214);
assert.equal(G.lineAngle(line), 0);
const resized = G.resizeLine(line, 350, 90);
assert.equal(G.lineLength(resized), 350);
assert.equal(G.lineAngle(resized), 90);
const moved = G.translateObject(resized, -125, 480);
assert.equal(G.lineLength(moved), 350);
assert.equal(moved.geometry.start.x, -125);
assert.equal(moved.geometry.start.y, 480);

const rectangle = G.rectangle("R1", G.point(10, 20), 300, 450);
assert.equal(rectangle.geometry.widthMm, 300);
assert.equal(rectangle.geometry.heightMm, 450);
const square = G.rectangleFromPoints("S1", G.point(0, 0), G.point(80, 35), true);
assert.equal(square.geometry.widthMm, 80);
assert.equal(square.geometry.heightMm, 80);

const circle = G.circle("C1", G.point(500, 600), 125);
assert.equal(circle.geometry.radiusMm, 125);
const movedCircle = G.translateObject(circle, 20, -30);
assert.deepEqual(movedCircle.geometry.center, G.point(520, 570));

const arc = G.arc("A1", G.point(0, 0), 100, 0, 90);
assert.deepEqual(G.arcStart(arc), G.point(100, 0));
assert.deepEqual(G.arcEnd(arc), G.point(0, 100));
assert.equal(G.arcLength(arc), 157.08);
assert.deepEqual(G.arcMid(arc), G.point(70.711, 70.711));

const smartPath = G.path("P1", [G.point(0, 0), G.point(100, 0), G.point(100, 100)], true);
assert.equal(smartPath.type, "path");
assert.equal(smartPath.geometry.closed, true);
assert.equal(smartPath.geometry.points.length, 3);
assert.equal(G.pathLength(smartPath), 341.421);
const movedPath = G.translateObject(smartPath, 25, 40);
assert.deepEqual(movedPath.geometry.points[0], G.point(25, 40));
assert.equal(G.pathLength(movedPath), G.pathLength(smartPath), "Moving a path must never alter its exact mm length");
const insertedPath = G.insertPathPoint(smartPath, 0, G.point(50, 0));
assert.equal(insertedPath.geometry.points.length, 4);
assert.equal(G.pathLength(insertedPath), G.pathLength(smartPath), "Adding a node on an existing segment preserves geometry length");
const removedPath = G.removePathPoint(insertedPath, 1);
assert.equal(removedPath.geometry.points.length, 3);
assert.deepEqual(removedPath.geometry.points, smartPath.geometry.points);
const editedPath = G.setPathPoint(smartPath, 1, G.point(120, 0));
assert.deepEqual(editedPath.geometry.points[1], G.point(120, 0));

let document = D.create({ widthMm: 800, heightMm: 2100 });
for (const object of [line, rectangle, circle, arc, smartPath]) document = D.addObject(document, object);
assert.equal(document.units, "mm");
assert.deepEqual(document.objects.map(object => object.type), ["line", "rectangle", "circle", "arc", "path"]);
assert.ok(D.SUPPORTED_TYPES.includes("path"));

const stored = P.toStored(document, { idx: 1, width_cm: 80, length_cm: 210 });
const envelope = JSON.parse(stored);
assert.equal(envelope.version, 1, "Server compatibility envelope remains on the validated drawing schema");
assert.equal(envelope.meta.authoritative, "door_drawing_v3");
assert.equal(envelope.meta.door_drawing_v3.units, "mm");
assert.deepEqual(envelope.elements.map(element => element.type), ["line", "rectangle", "ellipse", "pen", "pen"]);
assert.ok(envelope.elements[3].points.length >= 8, "Arc compatibility projection must contain enough display samples");
assert.deepEqual(envelope.elements[4].points[0], envelope.elements[4].points.at(-1), "Closed smart paths must remain visibly closed in the legacy compatibility projection");

const restored = P.fromStored(stored, { width_cm: 80, length_cm: 210 });
assert.equal(G.lineLength(restored.objects[0]), 214);
assert.equal(restored.objects[1].geometry.widthMm, 300);
assert.equal(restored.objects[2].geometry.radiusMm, 125);
assert.equal(restored.objects[3].geometry.sweepAngleDeg, 90);
assert.equal(G.arcLength(restored.objects[3]), 157.08, "Persistence roundtrip must preserve the exact circular arc, not the sampled compatibility pen");
assert.equal(restored.objects[4].type, "path");
assert.equal(restored.objects[4].geometry.closed, true);
assert.deepEqual(restored.objects[4].geometry.points, smartPath.geometry.points, "Smart path mm nodes must round-trip exactly through the authoritative V3 document");

assert.throws(() => G.circle("bad", G.point(0, 0), 0));
assert.throws(() => G.arc("bad", G.point(0, 0), 100, 0, 0));
assert.throws(() => G.path("bad", [G.point(0, 0)], false));
assert.throws(() => G.path("bad-closed", [G.point(0, 0), G.point(10, 0)], true));

console.log("Door Drawing V3 geometry/persistence tests passed");