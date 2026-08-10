"use strict";

const assert = require("node:assert/strict");
const path = require("node:path");

global.window = {};

require(path.resolve(__dirname, "../../public/js/door_cutting_order_sketch_engine.js"));
require(path.resolve(__dirname, "../../public/js/door_cutting_order_exact_line_model.js"));
require(path.resolve(__dirname, "../../public/js/door_cutting_order_exact_line_edit_model.js"));

const lineModel = window.AlmdinaExactLineModel;
const editModel = window.AlmdinaExactLineEditModel;
const transform = lineModel.createTransform(100, 80);

function line(id, start, length, angle) {
    const result = lineModel.buildElement({ transform, id, startCm: start, lengthCm: length, angleDeg: angle });
    assert.equal(result.valid, true);
    return result.element;
}

const base = line("a", [10, 10], 30, 0);
const resized = editModel.resize(base, transform, 40, 90, "start");
assert.equal(resized.valid, true);
assert.deepEqual(lineModel.exactMeta(resized.element).start_cm, [10, 10]);
assert.deepEqual(lineModel.exactMeta(resized.element).end_cm, [10, 50]);
assert.equal(lineModel.exactMeta(resized.element).length_cm, 40);
assert.equal(lineModel.exactMeta(resized.element).angle_deg, 90);

const anchoredEnd = editModel.resize(base, transform, 20, 0, "end");
assert.equal(anchoredEnd.valid, true);
assert.deepEqual(lineModel.exactMeta(anchoredEnd.element).end_cm, [40, 10]);
assert.deepEqual(lineModel.exactMeta(anchoredEnd.element).start_cm, [20, 10]);

const byEndpoints = editModel.buildFromEndpoints(base, transform, [5, 7], [8, 11]);
assert.equal(byEndpoints.valid, true);
assert.equal(lineModel.exactMeta(byEndpoints.element).length_cm, 5);
assert.equal(lineModel.exactMeta(byEndpoints.element).angle_deg, 53.13);

const first = line("first", [10, 10], 30, 0);
const second = line("second", [40, 10], 20, 90);
const changedFirst = editModel.resize(first, transform, 20, 0, "start");
const linked = editModel.applyEdit([first, second], "first", changedFirst.element, transform, { preserveConnections: true });
assert.equal(linked.valid, true);
assert.equal(linked.changedIds.length, 2);
assert.deepEqual(lineModel.exactMeta(linked.elements[0]).end_cm, [30, 10]);
assert.deepEqual(lineModel.exactMeta(linked.elements[1]).start_cm, [30, 10]);
assert.deepEqual(lineModel.exactMeta(linked.elements[1]).end_cm, [40, 30]);

const unlinked = editModel.applyEdit([first, second], "first", changedFirst.element, transform, { preserveConnections: false });
assert.equal(unlinked.valid, true);
assert.deepEqual(lineModel.exactMeta(unlinked.elements[1]).start_cm, [40, 10]);

assert.equal(editModel.connectedCount([first, second], "first", [40, 10]), 1);
assert.equal(editModel.axisAngle(line("reverse", [50, 20], 10, 180), "horizontal"), 180);
assert.equal(editModel.axisAngle(line("up", [50, 20], 10, -90), "vertical"), -90);

console.log("Exact line numeric editing model passed");