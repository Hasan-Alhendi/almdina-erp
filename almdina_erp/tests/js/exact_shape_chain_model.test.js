"use strict";

const assert = require("node:assert/strict");
const path = require("node:path");

global.window = {};

require(path.resolve(__dirname, "../../public/js/door_cutting_order_sketch_engine.js"));
require(path.resolve(__dirname, "../../public/js/door_cutting_order_special_shape_geometry.js"));
require(path.resolve(__dirname, "../../public/js/door_cutting_order_exact_line_model.js"));
require(path.resolve(__dirname, "../../public/js/door_cutting_order_exact_shape_chain_model.js"));

const lineModel = window.AlmdinaExactLineModel;
const chainModel = window.AlmdinaExactShapeChainModel;
const transform = lineModel.createTransform(100, 80);

function line(id, start, length, angle) {
    const result = lineModel.buildElement({ transform, id, startCm: start, lengthCm: length, angleDeg: angle });
    assert.equal(result.valid, true, `line ${id} should be valid`);
    return result.element;
}

const top = line("top", [0, 0], 100, 0);
const right = line("right", [100, 0], 80, 90);
const bottom = line("bottom", [100, 80], 100, 180);
const left = line("left", [0, 80], 80, -90);

const closed = chainModel.analyze([top, right, bottom, left], { width: 100, length: 80 });
assert.equal(closed.state, "exact-closed");
assert.equal(closed.closed, true);
assert.equal(closed.geometryValid, true);
assert.equal(closed.exactLineCount, 4);
assert.equal(closed.perimeterCm, 360);
assert.equal(closed.areaCm2, 8000);
assert.equal(closed.geometry.template, "exact-line-chain");
assert.equal(closed.points.length, 4);

const open = chainModel.analyze([top, right, bottom], { width: 100, length: 80 });
assert.equal(open.state, "open");
assert.equal(open.canAutoClose, true);
assert.equal(open.closeGapCm, 80);
assert.deepEqual(open.openEnds[0], [0, 0]);
assert.deepEqual(open.openEnds[1], [0, 80]);

const closing = chainModel.createClosingElement(open, transform, { id: "auto-close" });
assert.equal(closing.valid, true);
const autoClosed = chainModel.analyze([top, right, bottom, closing.element], { width: 100, length: 80 });
assert.equal(autoClosed.state, "exact-closed");
assert.equal(autoClosed.geometryValid, true);

const branch = line("branch", [100, 0], 30, 180);
const branched = chainModel.analyze([top, right, branch], { width: 100, length: 80 });
assert.equal(branched.state, "branched");

const detached = line("detached", [20, 20], 10, 0);
const disconnected = chainModel.analyze([top, detached], { width: 100, length: 80 });
assert.equal(disconnected.state, "disconnected");

const insetTop = line("i-top", [10, 10], 80, 0);
const insetRight = line("i-right", [90, 10], 60, 90);
const insetBottom = line("i-bottom", [90, 70], 80, 180);
const insetLeft = line("i-left", [10, 70], 60, -90);
const closedButNotBlankBounds = chainModel.analyze(
    [insetTop, insetRight, insetBottom, insetLeft],
    { width: 100, length: 80 }
);
assert.equal(closedButNotBlankBounds.state, "closed-invalid");
assert.equal(closedButNotBlankBounds.closed, true);
assert.equal(closedButNotBlankBounds.geometryValid, false);
assert.ok(closedButNotBlankBounds.geometryErrors.length > 0);

const serialized = chainModel.serializeGenerated(closed);
assert.ok(serialized.includes('"template":"exact-line-chain"'));
assert.equal(chainModel.isGeneratedGeometry(serialized), true);

console.log("Exact closed-shape chain model passed");
