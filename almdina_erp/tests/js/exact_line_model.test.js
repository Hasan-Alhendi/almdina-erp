"use strict";

const assert = require("node:assert/strict");
const path = require("node:path");

global.window = {};

require(path.resolve(__dirname, "../../public/js/door_cutting_order_sketch_engine.js"));
require(path.resolve(__dirname, "../../public/js/door_cutting_order_sketch_history.js"));
require(path.resolve(__dirname, "../../public/js/door_cutting_order_exact_line_model.js"));

const model = window.AlmdinaExactLineModel;
const history = window.AlmdinaSketchHistory;

assert.ok(Object.isFrozen(model));

const transform = model.createTransform(60, 100);
assert.ok(transform);
assert.equal(transform.widthCm, 60);
assert.equal(transform.lengthCm, 100);

const sourcePoint = [12.5, 44.25];
const canvasPoint = model.cmToCanvas(transform, sourcePoint);
const roundTrip = model.canvasToCm(transform, canvasPoint);
assert.ok(Math.abs(roundTrip[0] - sourcePoint[0]) < 0.002);
assert.ok(Math.abs(roundTrip[1] - sourcePoint[1]) < 0.002);

let result = model.buildElement({
    transform,
    startCm: [5, 10],
    lengthCm: 45,
    angleDeg: 0,
    id: "line-1",
});
assert.equal(result.valid, true);
assert.deepEqual(result.element.exact_line.start_cm, [5, 10]);
assert.deepEqual(result.element.exact_line.end_cm, [50, 10]);
assert.equal(result.element.exact_line.length_cm, 45);
assert.equal(result.element.exact_line.angle_deg, 0);

result = model.buildElement({
    transform,
    startCm: [10, 20],
    lengthCm: 35,
    angleDeg: 90,
    id: "line-2",
});
assert.equal(result.valid, true);
assert.deepEqual(result.element.exact_line.end_cm, [10, 55]);
assert.equal(model.axisLockedAngle([10, 10], [50, 14]), 0);
assert.equal(model.axisLockedAngle([10, 10], [12, 2]), -90);

const outside = model.buildElement({
    transform,
    startCm: [50, 10],
    lengthCm: 20,
    angleDeg: 0,
    id: "outside",
});
assert.equal(outside.valid, false);
assert.equal(outside.reason, "outside-piece");
assert.equal(outside.maximumLengthCm, 10);

const first = model.buildElement({
    transform,
    startCm: [0, 0],
    lengthCm: 20,
    angleDeg: 0,
    id: "snap-source",
}).element;
const snapped = model.nearestEndpoint([20.3, 0.2], [first], 0.6);
assert.ok(snapped);
assert.deepEqual(snapped.point, [20, 0]);
assert.equal(snapped.role, "end");

assert.deepEqual(model.command("45"), { valid: true, lengthCm: 45, angleDeg: null });
assert.deepEqual(model.command("45@30"), { valid: true, lengthCm: 45, angleDeg: 30 });

const seed = history.createState([]);
const host = {
    root: {},
    svg: {},
    elements: seed.elements,
    undo: seed.undo,
    redo: seed.redo,
    selectedId: "",
    hasChanges: false,
};
history.selectElement(host, "");
assert.equal(history.getActiveState(), host, "History operations must publish the real host editor state");

console.log("Exact smart-line model and live-state bridge passed");
