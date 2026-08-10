"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const uxSource = fs.readFileSync(
    path.resolve(__dirname, "../../public/js/door_cutting_order_exact_shape_chain_ux.js"),
    "utf8"
);

for (const marker of [
    "syncGeometryAfterSave",
    "controller.saveRequested",
    "special_shape_geometry_json = serialized",
    "special_shape_geometry_json = \"\"",
    "أُبقي الشكل الهندسي الدقيق الموجود لأنه من مصدر آخر",
    "الحدود أصبحت تحتوي قوسًا دائريًا دقيقًا",
    "لن يبقى DXF مستقيم قديم لا يطابق الرسم",
]) {
    assert.ok(uxSource.includes(marker), `Save synchronization should include ${marker}`);
}

console.log("Exact curved-shape save synchronization contract passed");
