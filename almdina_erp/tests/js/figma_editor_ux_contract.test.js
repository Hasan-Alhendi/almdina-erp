"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const publicJs = path.resolve(__dirname, "../../public/js");
const modelPath = path.join(publicJs, "door_cutting_order_figma_interaction_model.js");
const uxPath = path.join(publicJs, "door_cutting_order_figma_editor_ux.js");
const hooksPath = path.resolve(__dirname, "../../hooks.py");
const modelSource = fs.readFileSync(modelPath, "utf8");
const source = fs.readFileSync(uxPath, "utf8");
const hooks = fs.readFileSync(hooksPath, "utf8");

assert.doesNotThrow(() => new Function(modelSource), "Figma interaction model must remain valid JavaScript");
assert.doesNotThrow(() => new Function(source), "Figma editor UX must remain valid JavaScript");

for (const marker of [
    "الخصائص",
    "بدون Layers",
    "dco-figma-dock",
    "ضلع",
    "data-figma-line-length",
    "data-figma-line-angle",
    "data-figma-endpoint",
    "Ctrl+C نسخ",
    "Ctrl+V لصق",
    "Ctrl+D تكرار",
    "interaction.applyEndpointDrag",
    "segmentModel.resizeLine",
    "segmentModel.resizeArc",
    "dco-smart-template-palette.dco-drawing-workspace-gallery",
]) {
    assert.ok(source.includes(marker), `Figma editor UX should include ${marker}`);
}

const segmentModel = hooks.indexOf("door_cutting_order_exact_segment_dimension_model.js");
const figmaModel = hooks.indexOf("door_cutting_order_figma_interaction_model.js");
const workspace = hooks.indexOf("door_cutting_order_drawing_workspace_ux.js");
const figmaUx = hooks.indexOf("door_cutting_order_figma_editor_ux.js");
const closeUx = hooks.indexOf("door_cutting_order_special_shape_close_ux.js");
assert.ok(segmentModel >= 0 && figmaModel > segmentModel, "Figma interaction model must load after exact segment model");
assert.ok(figmaUx > workspace, "Figma editor UX must load after drawing workspace UX");
assert.ok(closeUx > figmaUx, "Figma editor UX must load before modal close guard");

console.log("Figma-like professional drawing editor UX contract passed");
