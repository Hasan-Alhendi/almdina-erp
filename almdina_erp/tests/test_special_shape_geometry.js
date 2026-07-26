"use strict";

const assert = require("node:assert/strict");
const path = require("node:path");

global.window = {};

require(path.resolve(
    __dirname,
    "../public/js/door_cutting_order_special_shape_geometry.js"
));

const geometry = window.AlmdinaSpecialShapeGeometry;
const width = 80;
const length = 200;

[
    "single-slope",
    "double-clipped",
    "trapezoid",
    "l-notch",
    "arch",
    "custom",
].forEach(template => {
    const payload = geometry.create(template, width, length);
    const result = geometry.validate(payload, width, length);
    assert.equal(result.valid, true, `${template} must produce valid exact geometry`);
    assert.ok(payload.points.length >= 3, `${template} must have at least three vertices`);
    assert.ok(payload.points.length <= geometry.MAX_VERTICES, `${template} must stay within the vertex limit`);
});

const bowTie = geometry.create("custom", width, length, [
    [0, 0],
    [width, length],
    [width, 0],
    [0, length],
]);
assert.equal(geometry.validate(bowTie, width, length).valid, false);
assert.equal(geometry.hasSelfIntersection(bowTie.points), true);

const outside = geometry.create("custom", width, length, [
    [0, 0],
    [width + 1, 0],
    [width, length],
    [0, length],
]);
assert.equal(geometry.validate(outside, width, length).valid, false);

const mismatched = geometry.create("single-slope", width, length);
assert.equal(geometry.validate(mismatched, width + 1, length).valid, false);

const piece = {
    piece_type: "Special",
    original_w: width,
    original_h: length,
    w: width,
    h: length,
    rotated: false,
    special_shape_geometry_json: geometry.serialize(
        geometry.create("single-slope", width, length)
    ),
};
assert.equal(geometry.isExact(piece), true);
assert.deepEqual(geometry.points(piece, width, length), geometry.fromPiece(piece).points);

const rotated = {
    ...piece,
    rotated: true,
    w: length,
    h: width,
};
const rotatedPoints = geometry.points(rotated, length, width);
assert.deepEqual(
    rotatedPoints[0],
    [length, geometry.templatePoints("single-slope", width, length)[0][0]],
    "A clockwise rotation must move the top-left slope to the correct new orientation"
);
assert.deepEqual(rotatedPoints.at(-1), [0, 0]);

const dxf = geometry.dxfPoints(piece, 100, 300, width * 10, length * 10);
assert.deepEqual(
    dxf[0],
    [100 + geometry.templatePoints("single-slope", width, length)[0][0] * 10, 2300],
    "DXF must translate centimetres to the supplied millimetre viewport and flip Y"
);
assert.equal(dxf.length, geometry.fromPiece(piece).points.length);

assert.equal(
    geometry.isExact({
        ...piece,
        original_w: width + 5,
    }),
    false,
    "A geometry saved for an old width must not silently become a cut path"
);

console.log("Special-shape exact geometry templates, validation, rotation, and DXF checks passed");
