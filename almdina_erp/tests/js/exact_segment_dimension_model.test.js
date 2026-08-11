"use strict";

const assert = require("node:assert/strict");
const path = require("node:path");

global.window = {};
require(path.resolve(__dirname, "../../public/js/door_cutting_order_sketch_engine.js"));
require(path.resolve(__dirname, "../../public/js/door_cutting_order_exact_line_model.js"));
require(path.resolve(__dirname, "../../public/js/door_cutting_order_exact_line_edit_model.js"));
require(path.resolve(__dirname, "../../public/js/door_cutting_order_exact_arc_model.js"));
require(path.resolve(__dirname, "../../public/js/door_cutting_order_exact_segment_dimension_model.js"));

const lineModel = window.AlmdinaExactLineModel;
const arcModel = window.AlmdinaExactArcModel;
const model = window.AlmdinaExactSegmentDimensionModel;
const transform = lineModel.createTransform(120, 90);

function line(id, start, length, angle) {
    const result = lineModel.buildElement({ transform, id, startCm: start, lengthCm: length, angleDeg: angle });
    assert.equal(result.valid, true);
    return result.element;
}

const first = line("line-1", [0, 0], 60, 0);
const second = line("line-2", [60, 0], 40, 90);
const arcResult = arcModel.fromLine(first, transform, 10, 1);
assert.equal(arcResult.valid, true);
const arc = arcResult.element;

const descriptors = model.descriptors([first, arc, { id: "note", type: "note" }]);
assert.equal(descriptors.length, 2);
assert.equal(descriptors[0].kind, "line");
assert.equal(descriptors[1].kind, "arc");
assert.equal(descriptors[0].lengthCm, 60);
assert.equal(descriptors[1].chordCm, 60);
assert.equal(descriptors[1].riseCm, 10);

const resizedLine = model.resizeLine(first, transform, { lengthCm: 50, angleDeg: 0, anchor: "start" });
assert.equal(resizedLine.valid, true);
assert.deepEqual(lineModel.exactMeta(resizedLine.element).end_cm, [50, 0]);

const resizedArc = model.resizeArc(arc, transform, { chordCm: 50, riseCm: 8, anchor: "start" });
assert.equal(resizedArc.valid, true);
assert.equal(arcModel.arcMeta(resizedArc.element).chord_cm, 50);
assert.equal(arcModel.arcMeta(resizedArc.element).rise_cm, 8);
assert.deepEqual(arcModel.arcMeta(resizedArc.element).start_cm, [0, 0]);
assert.deepEqual(arcModel.arcMeta(resizedArc.element).end_cm, [50, 0]);

const linked = model.applyEdit([first, second], "line-1", resizedLine.element, transform, { preserveConnections: true });
assert.equal(linked.valid, true);
assert.deepEqual(lineModel.exactMeta(linked.elements[1]).start_cm, [50, 0]);
assert.deepEqual(lineModel.exactMeta(linked.elements[1]).end_cm, [60, 40]);

const arcSecond = arcModel.fromLine(second, transform, 5, 1);
assert.equal(arcSecond.valid, true);
const linkedArc = model.applyEdit([first, arcSecond.element], "line-1", resizedLine.element, transform, { preserveConnections: true });
assert.equal(linkedArc.valid, true);
assert.deepEqual(arcModel.arcMeta(linkedArc.elements[1]).start_cm, [50, 0]);
assert.deepEqual(arcModel.arcMeta(linkedArc.elements[1]).end_cm, [60, 40]);
assert.equal(arcModel.arcMeta(linkedArc.elements[1]).rise_cm, 5);

const independent = model.applyEdit([first, second], "line-1", resizedLine.element, transform, { preserveConnections: false });
assert.equal(independent.valid, true);
assert.deepEqual(lineModel.exactMeta(independent.elements[1]).start_cm, [60, 0]);

console.log("Exact segment all-element dimension model passed");
