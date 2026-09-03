"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.resolve(__dirname, "../..");
const sources = [
    "public/js/door_cutting_order/drawing/door_cutting_order_special_shape_geometry.js",
    "public/js/door_cutting_order/drawing/door_cutting_order_shape_output_contract.js",
    "public/js/door_cutting_order/drawing/door_cutting_order_clipped_corner_ux.js",
    "public/js/door_cutting_order/cutting_plan/door_cutting_order_piece_geometry.js",
];

const fakeWindow = {};
const context = vm.createContext({
    window: fakeWindow,
    document: { documentElement: { lang: "ar" } },
    frappe: { boot: { lang: "ar" } },
    console: { log: console.log, error() {} },
    JSON,
    Number,
    String,
    Math,
    Object,
    Array,
    Map,
});
sources.forEach(relativePath => {
    vm.runInContext(fs.readFileSync(path.join(root, relativePath), "utf8"), context, {
        filename: path.basename(relativePath),
    });
});

const geometry = fakeWindow.AlmdinaCuttingPlanPieceGeometry;
assert.ok(geometry);

function dxfPiece(outer, holes = [], extra = {}) {
    return {
        id: 1,
        label: "1.1",
        x: 0,
        y: 0,
        w: 10,
        h: 10,
        piece_type: "Special",
        rotated: false,
        geometry: {
            schema_version: 1,
            unit: "mm",
            coordinate_space: "usable_sheet",
            outer,
            holes,
        },
        ...extra,
    };
}

function pathCommandCount(model, command) {
    return (model.geometry.pathData.match(new RegExp(`\\b${command}`, "g")) || []).length;
}

function assertLabelInside(model) {
    const point = [model.labelPoint.xPercent, model.labelPoint.yPercent];
    assert.equal(
        geometry.pointInMaterial(point, model.geometry.outer, model.geometry.holes),
        true,
        `${model.source} label must remain inside material`
    );
}

const legacyRectangle = geometry.resolve({ x: 2, y: 3, w: 30, h: 50, piece_type: "Regular" });
assert.equal(legacyRectangle.source, "rectangle");
assert.equal(legacyRectangle.vector, false);
assert.deepEqual(
    JSON.parse(JSON.stringify(legacyRectangle.placement)),
    { xCm: 2, yCm: 3, widthCm: 30, heightCm: 50, rotationDegrees: 0, mirrored: false }
);

const lShape = geometry.resolve(dxfPiece([
    [200, 300], [300, 300], [300, 400], [260, 400], [260, 340], [200, 340],
]));
assert.equal(lShape.source, "dxf");
assert.equal(lShape.vector, true);
assert.equal(lShape.exact, true);
assert.equal(lShape.placement.xCm, 20);
assert.equal(lShape.placement.yCm, 30);
assert.equal(lShape.placement.widthCm, 10);
assert.equal(lShape.placement.heightCm, 10);
assert.equal(pathCommandCount(lShape, "L"), 5);
assertLabelInside(lShape);

const zShape = geometry.resolve(dxfPiece([
    [0, 0], [100, 0], [100, 20], [35, 80], [100, 80],
    [100, 100], [0, 100], [0, 80], [65, 20], [0, 20],
]));
assert.equal(pathCommandCount(zShape, "L"), 9);
assertLabelInside(zShape);

const starPoints = [];
for (let index = 0; index < 10; index += 1) {
    const angle = -Math.PI / 2 + index * Math.PI / 5;
    const radius = index % 2 === 0 ? 50 : 22;
    starPoints.push([50 + Math.cos(angle) * radius, 50 + Math.sin(angle) * radius]);
}
const star = geometry.resolve(dxfPiece(starPoints));
assert.equal(star.geometry.outer.length, 10);
assert.equal(star.vector, true);
assertLabelInside(star);

const flowerPoints = [];
for (let index = 0; index < 32; index += 1) {
    const angle = index * Math.PI / 16;
    const radius = index % 2 === 0 ? 50 : 38;
    flowerPoints.push([55 + Math.cos(angle) * radius, 55 + Math.sin(angle) * radius]);
}
const flower = geometry.resolve(dxfPiece(flowerPoints));
assert.equal(flower.geometry.outer.length, 32);
assertLabelInside(flower);

const tessellatedCircle = [];
for (let index = 0; index < 48; index += 1) {
    const angle = index * Math.PI * 2 / 48;
    tessellatedCircle.push([100 + Math.cos(angle) * 75, 100 + Math.sin(angle) * 75]);
}
const curved = geometry.resolve(dxfPiece(tessellatedCircle));
assert.equal(curved.geometry.outer.length, 48);
assert.equal(pathCommandCount(curved, "L"), 47);
assertLabelInside(curved);

const withHole = geometry.resolve(dxfPiece(
    [[0, 0], [100, 0], [100, 100], [0, 100]],
    [[[35, 35], [65, 35], [65, 65], [35, 65]]]
));
assert.equal(withHole.vector, true);
assert.equal(pathCommandCount(withHole, "M"), 2);
assert.equal(geometry.pointInMaterial([50, 50], withHole.geometry.outer, withHole.geometry.holes), false);
assertLabelInside(withHole);

const alreadyRotatedDxf = geometry.resolve(dxfPiece(
    [[400, 100], [500, 100], [500, 160], [440, 160], [440, 200], [400, 200]],
    [],
    { x: 10, y: 40, w: 10, h: 10, rotated: true }
));
assert.equal(alreadyRotatedDxf.placement.xCm, 40);
assert.equal(alreadyRotatedDxf.placement.yCm, 10);
assert.equal(alreadyRotatedDxf.placement.rotationDegrees, 0);

const manualGeometry = fakeWindow.AlmdinaSpecialShapeGeometry.create("l-notch", 30, 50);
const manualRotated = geometry.resolve({
    x: 4,
    y: 5,
    w: 50,
    h: 30,
    original_w: 30,
    original_h: 50,
    piece_type: "Special",
    rotated: true,
    special_shape_geometry_json: fakeWindow.AlmdinaSpecialShapeGeometry.serialize(manualGeometry),
});
assert.equal(manualRotated.source, "manual-special");
assert.equal(manualRotated.placement.rotationDegrees, 90);
assert.equal(manualRotated.placement.widthCm, 50);
assert.equal(manualRotated.placement.heightCm, 30);
assertLabelInside(manualRotated);

const corner = geometry.resolve({
    x: 0,
    y: 0,
    w: 60,
    h: 80,
    original_w: 60,
    original_h: 80,
    piece_type: "L-Shaped Corner",
    clipped_corner_position: "Top Right",
    clipped_corner_width_cm: 20,
    clipped_corner_length_cm: 20,
    rotated: false,
});
assert.equal(corner.source, "corner");
assert.equal(corner.geometry.outer.length, 6);
assertLabelInside(corner);

const invalidDeclared = geometry.resolve(dxfPiece([[0, 0], [1, 1]]));
assert.equal(invalidDeclared.source, "invalid-dxf");
assert.equal(invalidDeclared.invalid, true);
assert.equal(invalidDeclared.exact, false);

console.log("Cutting-plan canonical piece geometry tests passed");
