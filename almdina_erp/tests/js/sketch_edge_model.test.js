"use strict";

const assert = require("node:assert/strict");
const path = require("node:path");

global.window = {};

require(path.resolve(__dirname, "../../public/js/door_cutting_order_sketch_engine.js"));
require(path.resolve(__dirname, "../../public/js/door_cutting_order_sketch_edge_model.js"));

const model = window.AlmdinaSketchEdgeModel;

const rectangle = [
    [100, 100],
    [300, 100],
    [300, 260],
    [100, 260],
    [100, 100],
];

assert.equal(model.orientation(rectangle, 0), "horizontal");
assert.equal(model.orientation(rectangle, 1), "vertical");
assert.equal(Math.round(model.edge(rectangle, 0).length), 200);

let moved = model.moveEdge(rectangle, 0, 40, 30, { width: 1000, height: 650 });
assert.deepEqual(moved[0], [140, 130]);
assert.deepEqual(moved[1], [340, 130]);
assert.deepEqual(moved[0], moved[moved.length - 1], "closed templates must remain closed");

let delta = model.perpendicularDragDelta(rectangle, 0, 80, 35, false);
assert.deepEqual(delta, { dx: 0, dy: 35 }, "horizontal edges should resize by vertical dragging");
delta = model.perpendicularDragDelta(rectangle, 1, 80, 35, false);
assert.deepEqual(delta, { dx: 80, dy: 0 }, "vertical edges should resize by horizontal dragging");

const angled = [
    [100, 100],
    [260, 190],
    [260, 300],
    [100, 300],
    [100, 100],
];
delta = model.perpendicularDragDelta(angled, 0, 20, 60, true);
assert.deepEqual(delta, { dx: 0, dy: 60 }, "Shift should constrain an angled-edge drag to one axis");

let aligned = model.alignEdge(angled, 0, "horizontal", { width: 1000, height: 650 });
assert.equal(model.orientation(aligned, 0), "horizontal");
assert.ok(Math.abs(model.edge(aligned, 0).length - model.edge(angled, 0).length) < 0.01);

aligned = model.alignEdge(angled, 0, "vertical", { width: 1000, height: 650 });
assert.equal(model.orientation(aligned, 0), "vertical");
assert.ok(Math.abs(model.edge(aligned, 0).length - model.edge(angled, 0).length) < 0.01);

const resized = model.setEdgeLength(rectangle, 0, 300, {
    width: 1000,
    height: 650,
    anchor: "center",
});
assert.equal(Math.round(model.edge(resized, 0).length), 300);
assert.deepEqual(resized[0], resized[resized.length - 1]);

const withMidpoint = model.insertMidpoint(rectangle, 0);
assert.equal(model.uniqueClosedPoints(withMidpoint).length, 5);
assert.deepEqual(model.uniqueClosedPoints(withMidpoint)[1], [200, 100]);
assert.deepEqual(withMidpoint[0], withMidpoint[withMidpoint.length - 1]);

console.log("Smart template edge model passed");
