"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const source = fs.readFileSync(path.resolve(
    __dirname,
    "../../public/js/door_cutting_order_exact_line_inspector_ux.js"
), "utf8");

for (const marker of ["الطول الحقيقي", "الزاوية", "X البداية", "Y النهاية", "أفقي", "عمودي"]) {
    assert.ok(source.includes(marker));
}

console.log("Exact line edit UX summary contract passed");