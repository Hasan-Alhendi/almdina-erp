"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const publicJs = path.resolve(__dirname, "../../public/js");
const uxPath = path.join(publicJs, "door_cutting_order_exact_line_ux.js");
const modelPath = path.join(publicJs, "door_cutting_order_exact_line_model.js");
const hooksPath = path.resolve(__dirname, "../../hooks.py");

const uxSource = fs.readFileSync(uxPath, "utf8");
const modelSource = fs.readFileSync(modelPath, "utf8");
const hooksSource = fs.readFileSync(hooksPath, "utf8");

assert.doesNotThrow(() => new Function(modelSource), "Exact-line model must remain valid JavaScript");
assert.doesNotThrow(() => new Function(uxSource), "Exact-line UX must remain valid JavaScript");

for (const marker of [
    "خط بمقاس حقيقي",
    "انقر البداية · وجّه · اكتب الطول · Enter",
    "data-exact-length",
    "data-exact-angle",
    "data-exact-axis=\"horizontal\"",
    "data-exact-axis=\"vertical\"",
    "45@30",
    "history.addElement",
    "model.nearestEndpoint",
]) {
    assert.ok(uxSource.includes(marker), `Exact-line UX should include ${marker}`);
}

const modelIndex = hooksSource.indexOf("door_cutting_order_exact_line_model.js");
const editorIndex = hooksSource.indexOf("door_cutting_order_special_shape_ux.js");
const uxIndex = hooksSource.indexOf("door_cutting_order_exact_line_ux.js");
const closeIndex = hooksSource.indexOf("door_cutting_order_special_shape_close_ux.js");
assert.ok(modelIndex >= 0 && modelIndex < editorIndex, "Exact-line model must load before the editor");
assert.ok(uxIndex > editorIndex, "Exact-line UX must wrap the final editor after it exists");
assert.ok(closeIndex > uxIndex, "Close guard must remain the outer editor wrapper");

console.log("Exact smart-line UX contract passed");
