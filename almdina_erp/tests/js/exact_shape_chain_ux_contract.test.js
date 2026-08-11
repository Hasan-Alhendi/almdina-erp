"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const publicJs = path.resolve(__dirname, "../../public/js");
const modelPath = path.join(publicJs, "door_cutting_order_exact_shape_chain_model.js");
const uxPath = path.join(publicJs, "door_cutting_order_exact_shape_chain_ux.js");
const hooksPath = path.resolve(__dirname, "../../hooks.py");

const modelSource = fs.readFileSync(modelPath, "utf8");
const uxSource = fs.readFileSync(uxPath, "utf8");
const hooksSource = fs.readFileSync(hooksPath, "utf8");

assert.doesNotThrow(() => new Function(modelSource), "Shape-chain model must remain valid JavaScript");
assert.doesNotThrow(() => new Function(uxSource), "Shape-chain UX must remain valid JavaScript");

for (const marker of [
    "الشكل الهندسي",
    "المسار مفتوح",
    "إغلاق المسار بخط دقيق",
    "exact-closed-curved",
    "قوس دائري دقيق",
    "المحيط الحقيقي",
    "special_shape_geometry_json",
    "chainModel.serializeGenerated",
    "chainModel.isGeneratedGeometry",
    "history.addElement",
]) {
    assert.ok(uxSource.includes(marker), `Shape-chain UX should include ${marker}`);
}

const lineModelIndex = hooksSource.indexOf("door_cutting_order_exact_line_model.js");
const editModelIndex = hooksSource.indexOf("door_cutting_order_exact_line_edit_model.js");
const arcModelIndex = hooksSource.indexOf("door_cutting_order_exact_arc_model.js");
const chainModelIndex = hooksSource.indexOf("door_cutting_order_exact_shape_chain_model.js");
const editorIndex = hooksSource.indexOf("door_cutting_order_special_shape_ux.js");
const inspectorIndex = hooksSource.indexOf("door_cutting_order_exact_line_inspector_ux.js");
const arcUxIndex = hooksSource.indexOf("door_cutting_order_exact_arc_ux.js");
const chainUxIndex = hooksSource.indexOf("door_cutting_order_exact_shape_chain_ux.js");
const closeIndex = hooksSource.indexOf("door_cutting_order_special_shape_close_ux.js");
assert.ok(lineModelIndex >= 0 && editModelIndex > lineModelIndex);
assert.ok(arcModelIndex > editModelIndex && chainModelIndex > arcModelIndex && chainModelIndex < editorIndex);
assert.ok(arcUxIndex > inspectorIndex && chainUxIndex > arcUxIndex && chainUxIndex < closeIndex);

console.log("Exact curved-shape UX contract passed");
