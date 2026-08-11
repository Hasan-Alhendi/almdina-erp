"use strict";

const assert = require("node:assert/strict");
const path = require("node:path");

global.window = {};

require(path.resolve(__dirname, "../../public/js/door_cutting_order_sketch_engine.js"));
require(path.resolve(__dirname, "../../public/js/door_cutting_order_exact_line_model.js"));
require(path.resolve(__dirname, "../../public/js/door_cutting_order_exact_arc_model.js"));

const lineModel = window.AlmdinaExactLineModel;
const arcModel = window.AlmdinaExactArcModel;
const transform = lineModel.createTransform(100, 80);

const source = lineModel.buildElement({
    transform,
    id: "top",
    startCm: [0, 20],
    lengthCm: 100,
    angleDeg: 0,
});
assert.equal(source.valid, true);

const converted = arcModel.fromLine(source.element, transform, 10, 1);
assert.equal(converted.valid, true);
const meta = arcModel.arcMeta(converted.element);
assert.ok(meta);
assert.deepEqual(meta.start_cm, [0, 20]);
assert.deepEqual(meta.end_cm, [100, 20]);
assert.equal(meta.chord_cm, 100);
assert.equal(meta.rise_cm, 10);
assert.equal(meta.radius_cm, 130);
assert.deepEqual(meta.apex_cm, [50, 30]);
assert.ok(meta.length_cm > 100);
assert.ok(converted.element.points.length >= 20);
assert.ok(arcModel.svgArcPath(converted.element, transform).includes(" A "));

const samples = arcModel.sampleCm(converted.element);
assert.deepEqual(samples[0], [0, 20]);
assert.deepEqual(samples[samples.length - 1], [100, 20]);
assert.ok(samples.every(point => point[0] >= 0 && point[0] <= 100 && point[1] >= 0 && point[1] <= 80));

const flipped = arcModel.flip(converted.element, transform);
assert.equal(flipped.valid, true);
assert.equal(arcModel.arcMeta(flipped.element).side, -1);
assert.deepEqual(arcModel.arcMeta(flipped.element).apex_cm, [50, 10]);

const straight = arcModel.toLine(converted.element, transform);
assert.equal(straight.valid, true);
assert.ok(lineModel.exactMeta(straight.element));
assert.equal(arcModel.arcMeta(straight.element), null);
assert.deepEqual(lineModel.exactMeta(straight.element).start_cm, [0, 20]);
assert.deepEqual(lineModel.exactMeta(straight.element).end_cm, [100, 20]);

const boundaryLine = lineModel.buildElement({
    transform,
    id: "boundary",
    startCm: [0, 0],
    lengthCm: 100,
    angleDeg: 0,
});
assert.equal(boundaryLine.valid, true);
const outside = arcModel.fromLine(boundaryLine.element, transform, 10, -1);
assert.equal(outside.valid, false);
assert.equal(outside.reason, "arc-outside-piece");

const limits = arcModel.limits([0, 0], [100, 0]);
assert.equal(limits.maximum, 49);
assert.ok(limits.defaultRise > 0 && limits.defaultRise < limits.maximum);

console.log("Exact circular arc model passed");
