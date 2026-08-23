"use strict";

const assert = require("node:assert/strict");
const path = require("node:path");

global.window = {};

require(path.resolve(
    __dirname,
    "../../public/js/door_cutting_order/drawing/door_cutting_order_special_shape_geometry.js"
));
require(path.resolve(
    __dirname,
    "../../public/js/door_cutting_order/drawing/door_cutting_order_shape_output_contract.js"
));

const geometry = window.AlmdinaSpecialShapeGeometry;
const contract = window.AlmdinaShapeOutputContract;

assert.equal(Object.isFrozen(contract), true, "The output contract API must be immutable");

const drawingRaw = JSON.stringify({
    schema: "almdina.special-shape-documentation",
    version: 1,
    canvas: { widthMm: 800, heightMm: 2000 },
    reference: null,
    elements: [
        {
            id: "note-1",
            type: "text",
            position: { xMm: 500, yMm: 320 },
            text: "قص مائل",
        },
    ],
    notes: "",
    source: "pen",
    templateId: null,
});
const parsedDrawing = contract.parseDrawing(drawingRaw);
assert.ok(parsedDrawing);
assert.equal(Object.isFrozen(parsedDrawing), true);
assert.equal(Object.isFrozen(parsedDrawing.elements), true);
assert.equal(Object.isFrozen(parsedDrawing.elements[0]), true);
assert.equal(
    contract.parseDrawing(drawingRaw),
    parsedDrawing,
    "Repeated JSON reads should reuse the safe immutable parse"
);
assert.equal(contract.parseDrawing('{"schema":"almdina.special-shape-documentation","version":2,"elements":[]}'), null);
assert.equal(contract.parseDrawing('{"schema":"almdina.special-shape-documentation","version":1,"elements":"invalid"}'), null);
assert.equal(contract.parseDrawing("{"), null);

const geometryRaw = geometry.serialize(
    geometry.create("single-slope", 80, 200)
);
const objectGeometry = contract.parseGeometry(JSON.parse(geometryRaw));
assert.equal(Object.isFrozen(objectGeometry), true);
assert.equal(Object.isFrozen(objectGeometry.points), true);
const exactPiece = {
    piece_type: "Special",
    original_w: 80,
    original_h: 200,
    special_shape_geometry_json: geometryRaw,
};
const documentedPiece = {
    ...exactPiece,
    special_shape_drawing_json: drawingRaw,
};

assert.equal(contract.visual(documentedPiece).kind, "documentation");
assert.equal(
    contract.visual({ drawing_json: drawingRaw }).kind,
    "documentation",
    "Invoice and measurement aliases must use the same documentation payload"
);
assert.equal(contract.visual(exactPiece).kind, "geometry");
assert.equal(
    contract.visual({
        piece_type: "Special",
        width_cm: 80,
        length_cm: 200,
        geometry_json: geometryRaw,
    }).kind,
    "geometry",
    "Invoice and measurement aliases must use the same geometry fallback"
);
assert.equal(contract.hasVisual({ piece_type: "Regular" }), false);

assert.equal(contract.hasExactCutPath(exactPiece), true);
assert.equal(
    contract.pointsAttribute(exactPiece, 100, 100),
    geometry.pointsAttribute(exactPiece, 100, 100)
);
assert.deepEqual(
    contract.dxfPoints(exactPiece, 10, 20, 800, 2000),
    geometry.dxfPoints(exactPiece, 10, 20, 800, 2000)
);
assert.equal(
    contract.hasExactCutPath({ ...exactPiece, piece_type: "Regular" }),
    false,
    "Only an explicitly special piece may become an exact CNC path"
);
assert.deepEqual(
    contract.dxfPoints({ ...exactPiece, piece_type: "Regular" }, 0, 0, 800, 2000),
    []
);

console.log("Unified special-shape output contract checks passed");
