"use strict";

const assert = require("node:assert/strict");
const path = require("node:path");

global.window = {};

require(path.resolve(__dirname, "../../public/js/door_cutting_order_sketch_engine.js"));
require(path.resolve(__dirname, "../../public/js/door_cutting_order_sketch_edge_model.js"));

const model = window.AlmdinaSketchEdgeModel;

const rectangle = [
    [100, 100],
    [500, 100],
    [500, 400],
    [100, 400],
    [100, 100],
];

assert.ok(Object.isFrozen(model));
assert.equal(model.signedArea(rectangle) > 0, true);

const topFrame = model.edgeFrame(rectangle, 0);
assert.ok(topFrame);
assert.ok(topFrame.inward.y > 0, "Top edge inward normal must point inside the rectangle");

let result = model.createNotch(rectangle, 0, {
    featureWidth: 120,
    featureDepth: 60,
    width: 1000,
    height: 650,
});
assert.equal(result.changed, true);
assert.equal(result.feature.type, "notch");
assert.equal(model.uniqueClosedPoints(result.points).length, 8);
assert.deepEqual(result.points[0], result.points[result.points.length - 1]);

const notchPoints = model.uniqueClosedPoints(result.points);
assert.ok(
    notchPoints.some(point => point[1] > 100),
    "A notch on the top edge must move into the panel"
);

result = model.createProtrusion(rectangle, 2, {
    featureWidth: 110,
    featureDepth: 50,
    width: 1000,
    height: 650,
});
assert.equal(result.changed, true);
assert.equal(result.feature.type, "protrusion");
const protrusionPoints = model.uniqueClosedPoints(result.points);
assert.ok(
    protrusionPoints.some(point => point[1] > 400),
    "An outward protrusion on the bottom edge must extend away from the panel"
);

const diagonal = [
    [200, 120],
    [500, 200],
    [480, 430],
    [180, 390],
    [200, 120],
];
result = model.createNotch(diagonal, 0, {
    featureWidth: 80,
    featureDepth: 35,
    width: 1000,
    height: 650,
});
assert.equal(result.changed, true, "Notches should also work on angled edges");
assert.equal(result.feature.orientation, "angled");

const shortEdge = [
    [100, 100],
    [110, 100],
    [110, 200],
    [100, 200],
    [100, 100],
];
result = model.createNotch(shortEdge, 0, { featureWidth: 20, featureDepth: 20 });
assert.equal(result.changed, false);
assert.equal(result.reason, "edge-too-short");

console.log("Smart edge notch and protrusion features passed");
