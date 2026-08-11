"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const uxPath = path.resolve(__dirname, "../../public/js/door_cutting_order_figma_generic_handles_ux.js");
const hooksPath = path.resolve(__dirname, "../../hooks.py");
const source = fs.readFileSync(uxPath, "utf8");
const hooks = fs.readFileSync(hooksPath, "utf8");

assert.doesNotThrow(() => new Function(source), "Figma generic handles UX must remain valid JavaScript");
for (const marker of [
    "data-figma-generic-handle",
    'element.type === "rectangle"',
    'element.type === "ellipse"',
    'element.type === "line" || element.type === "dimension"',
    'element.type === "note"',
    "history.snapshot",
    "smart_template_editable",
]) {
    assert.ok(source.includes(marker), `Generic handles should include ${marker}`);
}

const figmaUx = hooks.indexOf("door_cutting_order_figma_editor_ux.js");
const genericUx = hooks.indexOf("door_cutting_order_figma_generic_handles_ux.js");
const closeUx = hooks.indexOf("door_cutting_order_special_shape_close_ux.js");
assert.ok(figmaUx >= 0 && genericUx > figmaUx, "Generic handles must load after figma editor UX");
assert.ok(closeUx > genericUx, "Generic handles must load before close guard");

console.log("Figma generic element handles UX contract passed");
