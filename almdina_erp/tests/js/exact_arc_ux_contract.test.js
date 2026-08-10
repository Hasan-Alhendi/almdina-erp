"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const publicJs = path.resolve(__dirname, "../../public/js");
const modelSource = fs.readFileSync(path.join(publicJs, "door_cutting_order_exact_arc_model.js"), "utf8");
const uxSource = fs.readFileSync(path.join(publicJs, "door_cutting_order_exact_arc_ux.js"), "utf8");
const hooksSource = fs.readFileSync(path.resolve(__dirname, "../../hooks.py"), "utf8");

assert.doesNotThrow(() => new Function(modelSource), "Exact-arc model must remain valid JavaScript");
assert.doesNotThrow(() => new Function(uxSource), "Exact-arc UX must remain valid JavaScript");

for (const marker of [
    "تحويل الضلع إلى قوس",
    "ارتفاع القوس",
    "نصف القطر",
    "طول القوس",
    "عكس جهة القوس",
    "إعادة لمستقيم",
    "قوس دائري بمعادلة هندسية",
    "arcModel.fromLine",
    "arcModel.rebuild",
    "arcModel.toLine",
    "history.snapshot",
]) {
    assert.ok(uxSource.includes(marker), `Exact-arc UX should include ${marker}`);
}

for (const marker of [
    "radius_cm",
    "rise_cm",
    "center_cm",
    "apex_cm",
    "length_cm",
    "svgArcPath",
    "arc-outside-piece",
]) {
    assert.ok(modelSource.includes(marker), `Exact-arc model should include ${marker}`);
}

const arcModelIndex = hooksSource.indexOf("door_cutting_order_exact_arc_model.js");
const chainModelIndex = hooksSource.indexOf("door_cutting_order_exact_shape_chain_model.js");
const editorIndex = hooksSource.indexOf("door_cutting_order_special_shape_ux.js");
const lineInspectorIndex = hooksSource.indexOf("door_cutting_order_exact_line_inspector_ux.js");
const arcUxIndex = hooksSource.indexOf("door_cutting_order_exact_arc_ux.js");
const chainUxIndex = hooksSource.indexOf("door_cutting_order_exact_shape_chain_ux.js");
assert.ok(arcModelIndex >= 0 && arcModelIndex < chainModelIndex && chainModelIndex < editorIndex);
assert.ok(arcUxIndex > lineInspectorIndex && arcUxIndex < chainUxIndex);

console.log("Exact smart arc UX contract passed");
