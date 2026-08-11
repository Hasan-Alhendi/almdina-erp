"use strict";

const assert = require("node:assert/strict");
const path = require("node:path");

global.window = {};
require(path.resolve(__dirname, "../../public/js/door_drawing_v2/domain/precision_policy.js"));
require(path.resolve(__dirname, "../../public/js/door_drawing_v2/domain/geometry_engine.js"));
require(path.resolve(__dirname, "../../public/js/door_drawing_v2/domain/document_model.js"));

const core = window.AlmdinaDoorDrawingV2;
const geometry = core.Geometry;
const documents = core.DocumentModel;

const line = documents.createObject("line", { start:{x:0,y:0}, end:{x:214,y:0} }, { id:"line-214" });
assert.equal(geometry.lineLength(line.geometry), 214, "A 214 mm line must stay 214 mm in world geometry");
assert.equal(geometry.lineAngleDeg(line.geometry), 0);

let document = documents.createDocument({ orderId:"DCO-TEST", rowId:"ROW-1", widthMm:800, heightMm:2100 });
document = documents.addObject(document, line);
assert.equal(document.units, "mm");
assert.equal(document.door.width, 800);
assert.equal(document.door.height, 2100);
const roundTrip = documents.parse(documents.serialize(document));
assert.equal(roundTrip.objects[0].geometry.end.x, 214, "Serialization must not change manufacturing geometry");

const invalidUnits = JSON.parse(documents.serialize(document));
invalidUnits.units = "cm";
assert.throws(() => documents.parse(invalidUnits), /units must be mm/);

const polygon = documents.createObject("polygon", { points:[{x:0,y:0},{x:800,y:0},{x:800,y:2100},{x:0,y:2100}] }, {id:"door-outline"});
assert.equal(geometry.polygonArea(polygon.geometry.points), 1680000);
assert.equal(geometry.polylineLength(polygon.geometry.points, true), 5800);

const bezier = { start:{x:0,y:0}, control1:{x:100,y:200}, control2:{x:200,y:200}, end:{x:300,y:0} };
const flattened = geometry.flattenCubicBezier(bezier, 0.05);
assert.deepEqual(flattened[0], {x:0,y:0});
assert.deepEqual(flattened.at(-1), {x:300,y:0});
assert.ok(flattened.length > 10, "Bezier flattening should be driven by geometric tolerance in mm");

console.log("Door Drawing V2 mm geometry/document tests passed");
