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
assert.equal(G.lineLength(line), 214, "214 mm in the model must remain exactly 214 mm");
assert.equal(G.lineAngle(line), 0);

const resized = G.resizeLine(line, 350, 90);
assert.equal(G.lineLength(resized), 350);
assert.equal(G.lineAngle(resized), 90);
assert.equal(resized.geometry.start.x, 0);
assert.equal(resized.geometry.start.y, 0);

const moved = G.translateLine(resized, -125, 480);
assert.equal(G.lineLength(moved), 350, "Moving a line must never change its physical length");
assert.equal(moved.geometry.start.x, -125);
assert.equal(moved.geometry.start.y, 480);

let document = D.create({ widthMm: 800, heightMm: 2100 });
document = D.addObject(document, line);
assert.equal(document.units, "mm");
assert.equal(document.objects.length, 1);

const stored = P.toStored(document, { idx: 1, width_cm: 80, length_cm: 210 });
const envelope = JSON.parse(stored);
assert.equal(envelope.version, 1, "Server compatibility envelope stays on the existing validated schema during migration");
assert.equal(envelope.meta.authoritative, "door_drawing_v3");
assert.equal(envelope.meta.door_drawing_v3.units, "mm");
assert.equal(envelope.meta.door_drawing_v3.objects[0].geometry.end.x, 214);

const restored = P.fromStored(stored, { width_cm: 80, length_cm: 210 });
assert.equal(G.lineLength(restored.objects[0]), 214, "Persistence roundtrip must not scale geometry with the screen");

console.log("Door Drawing V3 geometry/persistence tests passed");
