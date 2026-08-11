"use strict";

const assert = require("node:assert/strict");
const path = require("node:path");

global.window = {};

const publicJs = path.resolve(__dirname, "../../public/js");
require(path.join(publicJs, "door_drawing_v2/domain/precision_policy.js"));
require(path.join(publicJs, "door_drawing_v2/interaction/workspace_policy.js"));
require(path.join(publicJs, "door_cutting_order_sketch_engine.js"));
require(path.join(publicJs, "door_cutting_order_exact_line_model.js"));

const model = window.AlmdinaExactLineModel;
const parsed = model.command("214");
assert.equal(parsed.valid, true);
assert.equal(parsed.inputLengthMm, 214);
assert.equal(parsed.lengthCm, 21.4, "The transition adapter may store cm internally, but the V2 UI command is 214 mm");

const transform = model.createTransform(20, 215.6);
assert.equal(transform.freeWorkspace, true, "V2 workspace policy must opt the legacy transition model into free placement");

const outsideStart = [-85, 42];
assert.equal(model.insidePiece(transform, outsideStart), true, "Free workspace must not reject a point merely because it is outside the old piece frame");
assert.deepEqual(model.clampPointToPiece(transform, outsideStart), outsideStart, "Free workspace must not snap or clamp a point to the old blue frame");

const built = model.buildElement({
    transform,
    startCm: outsideStart,
    lengthCm: parsed.lengthCm,
    angleDeg: 0,
    id: "free-line",
});
assert.equal(built.valid, true);
assert.deepEqual(built.element.exact_line.start_cm, outsideStart);
assert.equal(built.element.exact_line.length_cm, 21.4);
assert.equal(built.element.exact_line.workspace, "free");

console.log("Door Drawing V2 exact-line free workspace tests passed");
