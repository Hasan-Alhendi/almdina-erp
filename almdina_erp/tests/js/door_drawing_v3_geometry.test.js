"use strict";

const assert = require("node:assert/strict");
const path = require("node:path");

global.window = {};
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/domain/geometry.js"));
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/domain/document.js"));
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/application/history.js"));
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/infrastructure/persistence_adapter.js"));

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

let document = D.create({ widthMm: 800, heightMm: 2100 });
for (const object of [line, rectangle, circle, arc]) document = D.addObject(document, object);
assert.equal(document.units, "mm");
assert.deepEqual(document.objects.map(object => object.type), ["line", "rectangle", "circle", "arc"]);

const stored = P.toStored(document, { idx: 1, width_cm: 80, length_cm: 210 });
const envelope = JSON.parse(stored);
assert.equal(envelope.version, 1, "Server compatibility envelope remains on the validated drawing schema");
assert.equal(envelope.meta.authoritative, "door_drawing_v3");
assert.equal(envelope.meta.door_drawing_v3.units, "mm");
assert.deepEqual(envelope.elements.map(element => element.type), ["line", "rectangle", "ellipse", "pen"]);
assert.ok(envelope.elements[3].points.length >= 8, "Arc compatibility projection must contain enough display samples");

const restored = P.fromStored(stored, { width_cm: 80, length_cm: 210 });
assert.equal(G.lineLength(restored.objects[0]), 214);
assert.equal(restored.objects[1].geometry.widthMm, 300);
assert.equal(restored.objects[2].geometry.radiusMm, 125);
assert.equal(restored.objects[3].geometry.sweepAngleDeg, 90);
assert.equal(G.arcLength(restored.objects[3]), 157.08, "Persistence roundtrip must preserve the exact circular arc, not the sampled compatibility pen");

assert.throws(() => G.circle("bad", G.point(0, 0), 0));
assert.throws(() => G.arc("bad", G.point(0, 0), 100, 0, 0));

console.log("Door Drawing V3 geometry/persistence tests passed");