"use strict";

const assert = require("node:assert/strict");
const path = require("node:path");

global.window = {};
require(path.resolve(__dirname, "../../public/js/door_cutting_order_sketch_engine.js"));
require(path.resolve(__dirname, "../../public/js/door_cutting_order_exact_line_model.js"));
require(path.resolve(__dirname, "../../public/js/door_cutting_order_exact_line_edit_model.js"));
require(path.resolve(__dirname, "../../public/js/door_cutting_order_exact_arc_model.js"));
require(path.resolve(__dirname, "../../public/js/door_cutting_order_exact_segment_dimension_model.js"));
require(path.resolve(__dirname, "../../public/js/door_cutting_order_figma_interaction_model.js"));

const lineModel = window.AlmdinaExactLineModel;
const interaction = window.AlmdinaFigmaInteractionModel;
const transform = lineModel.createTransform(120, 80);

const base = lineModel.buildElement({ transform, startCm: [10, 10], lengthCm: 40, angleDeg: 0, id: "line-a" });
assert.equal(base.valid, true);
assert.equal(interaction.elementKind(base.element), "exact-line");

const copy = interaction.duplicateElement(base.element, transform, { offsetCm: 2 });
assert.equal(copy.valid, true);
assert.notEqual(copy.element.id, base.element.id);
assert.deepEqual(copy.element.exact_line.start_cm, [12, 12]);
assert.equal(copy.element.exact_line.length_cm, 40);
assert.equal(copy.element.exact_line.angle_deg, 0);

const second = lineModel.buildElement({ transform, startCm: [50, 10], lengthCm: 30, angleDeg: 90, id: "line-b" });
assert.equal(second.valid, true);
const connected = [base.element, second.element];
const moved = interaction.applyEndpointDrag(connected, "line-a", "end", [45, 10], transform, { preserveConnections: true });
assert.equal(moved.valid, true);
const firstAfter = moved.elements.find(item => item.id === "line-a");
const secondAfter = moved.elements.find(item => item.id === "line-b");
assert.deepEqual(firstAfter.exact_line.end_cm, [45, 10]);
assert.deepEqual(secondAfter.exact_line.start_cm, [45, 10]);
assert.equal(firstAfter.exact_line.length_cm, 35);

const visual = { id: "rect-a", type: "rectangle", x: 100, y: 100, width: 120, height: 80, color: "#000" };
const visualCopy = interaction.duplicateElement(visual, transform, { offsetCanvas: 18 });
assert.equal(visualCopy.valid, true);
assert.notEqual(visualCopy.element.id, visual.id);
assert.equal(visualCopy.element.x, 118);
assert.equal(visualCopy.element.y, 118);

console.log("Figma-like geometry interaction model passed");
