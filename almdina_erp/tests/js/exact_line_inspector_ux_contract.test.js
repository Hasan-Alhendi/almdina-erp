"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const publicJs = path.resolve(__dirname, "../../public/js");
const modelPath = path.join(publicJs, "door_cutting_order_exact_line_edit_model.js");
const uxPath = path.join(publicJs, "door_cutting_order_exact_line_inspector_ux.js");
const hooksPath = path.resolve(__dirname, "../../hooks.py");

const modelSource = fs.readFileSync(modelPath, "utf8");
const uxSource = fs.readFileSync(uxPath, "utf8");
const hooksSource = fs.readFileSync(hooksPath, "utf8");

assert.doesNotThrow(() => new Function(modelSource), "Exact-line edit model must remain valid JavaScript");
assert.doesNotThrow(() => new Function(uxSource), "Exact-line inspector UX must remain valid JavaScript");

for (const marker of [
    "خصائص الخط الدقيق",
    "تطبيق الطول والزاوية",
    "تطبيق الإحداثيات",
    "ثبّت البداية",
    "ثبّت النهاية",
    "حافظ على اتصال الخطوط",
    "data-edit-length",
    "data-start-x",
    "editModel.applyEdit",
    "history.snapshot",
]) {
    assert.ok(uxSource.includes(marker), `Exact-line inspector UX should include ${marker}`);
}

const baseModelIndex = hooksSource.indexOf("door_cutting_order_exact_line_model.js");
const editModelIndex = hooksSource.indexOf("door_cutting_order_exact_line_edit_model.js");
const editorIndex = hooksSource.indexOf("door_cutting_order_special_shape_ux.js");
const exactUxIndex = hooksSource.indexOf("door_cutting_order_exact_line_ux.js");
const inspectorIndex = hooksSource.indexOf("door_cutting_order_exact_line_inspector_ux.js");
const closeIndex = hooksSource.indexOf("door_cutting_order_special_shape_close_ux.js");
assert.ok(baseModelIndex >= 0 && editModelIndex > baseModelIndex, "Edit model must load after the exact-line base model");
assert.ok(editModelIndex < editorIndex, "Pure edit model must load before editor wrappers");
assert.ok(inspectorIndex > exactUxIndex, "Inspector must wrap the exact-line creation UX");
assert.ok(closeIndex > inspectorIndex, "Close guard must remain the outer editor wrapper");

console.log("Exact line inspector UX contract passed");