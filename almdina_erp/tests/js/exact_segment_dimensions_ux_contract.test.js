"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const publicJs = path.resolve(__dirname, "../../public/js");
const modelSource = fs.readFileSync(path.join(publicJs, "door_cutting_order_exact_segment_dimension_model.js"), "utf8");
const uxSource = fs.readFileSync(path.join(publicJs, "door_cutting_order_exact_segment_dimensions_ux.js"), "utf8");
const hooksSource = fs.readFileSync(path.resolve(__dirname, "../../hooks.py"), "utf8");

assert.doesNotThrow(() => new Function(modelSource));
assert.doesNotThrow(() => new Function(uxSource));

for (const marker of [
    "قياسات جميع العناصر",
    "أدخل قياس كل ضلع وقوس",
    "طول الضلع",
    "طول الوتر",
    "ارتفاع القوس",
    "حافظ على اتصال العناصر",
    "Enter = تطبيق",
    "سنتيمتر",
    "dimensionModel.applyEdit",
    "history.snapshot",
    "dco-exact-measure-overlay",
]) {
    assert.ok(uxSource.includes(marker), `All-element dimension UX should include ${marker}`);
}

const arcModelIndex = hooksSource.indexOf("door_cutting_order_exact_arc_model.js");
const dimensionsModelIndex = hooksSource.indexOf("door_cutting_order_exact_segment_dimension_model.js");
const chainModelIndex = hooksSource.indexOf("door_cutting_order_exact_shape_chain_model.js");
const arcUxIndex = hooksSource.indexOf("door_cutting_order_exact_arc_ux.js");
const dimensionsUxIndex = hooksSource.indexOf("door_cutting_order_exact_segment_dimensions_ux.js");
const chainUxIndex = hooksSource.indexOf("door_cutting_order_exact_shape_chain_ux.js");
assert.ok(dimensionsModelIndex > arcModelIndex && dimensionsModelIndex < chainModelIndex);
assert.ok(dimensionsUxIndex > arcUxIndex && dimensionsUxIndex < chainUxIndex);

console.log("Exact all-element dimensions UX contract passed");
