"use strict";

const assert = require("node:assert/strict");
const path = require("node:path");

global.window = {};
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/domain/geometry.js"));
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/domain/document.js"));
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/domain/smart_path_domain.js"));
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/domain/text_annotation_domain.js"));
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/infrastructure/persistence_adapter.js"));
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/infrastructure/smart_path_persistence.js"));

const V3 = global.window.AlmdinaDoorDrawingV3;
const G = V3.Geometry;
const D = V3.DocumentModel;
const P = V3.PersistenceAdapter;

let documentModel = D.create({ widthMm: 800, heightMm: 2100 });
const note = G.text("txt-print", G.point(250, 600), "ملاحظة عربية", {
    fontSizeMm: 34,
    fill: "#172033",
});
documentModel = D.addObject(documentModel, note);

const stored = JSON.parse(P.toStored(documentModel, { idx: 7 }));
assert.equal(stored.meta.authoritative, "door_drawing_v3");
assert.equal(stored.meta.units, "mm");
assert.equal(stored.meta.door_drawing_v3.objects[0].type, "text");
assert.equal(stored.meta.door_drawing_v3.objects[0].geometry.position.x, 250);
assert.equal(stored.meta.door_drawing_v3.objects[0].geometry.position.y, 600);

const printable = stored.elements.find(element => element.id === "txt-print");
assert.ok(printable, "TXT annotation must have a compatibility note for the existing print renderer");
assert.equal(printable.type, "note");
assert.equal(printable.x, 25);
assert.equal(printable.y, 60);
assert.equal(printable.text, "ملاحظة عربية");
assert.equal(printable.font_size, 34);
assert.equal(printable.text_anchor, "end");

const restored = P.fromStored(JSON.stringify(stored), { width_cm: 80, length_cm: 210 });
const restoredNote = D.objectById(restored, "txt-print");
assert.equal(restoredNote.type, "text");
assert.equal(restoredNote.text, "ملاحظة عربية");
assert.equal(restoredNote.style.fontSizeMm, 34);
assert.deepEqual(restoredNote.geometry.position, G.point(250, 600));

console.log("Door Drawing V3 TXT annotation persistence/print tests passed");
