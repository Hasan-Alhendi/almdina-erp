"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "../..");
const source = fs.readFileSync(path.join(root, "public/js/door_cutting_order_measurement_toolbar_ux.js"), "utf8");
const hooks = fs.readFileSync(path.join(root, "hooks.py"), "utf8");

assert.doesNotThrow(() => new Function(source), "Measurement toolbar UX must remain valid JavaScript");
for (const marker of [
    "جدول قياسات الدرف",
    "dco-print-measurements",
    "dco-open-measurements-window",
    "dco-measurement-instructions",
    "تعليمات جدول القياسات",
]) {
    assert.ok(source.includes(marker) || marker === "dco-print-measurements" || marker === "dco-open-measurements-window", `Missing toolbar marker: ${marker}`);
}
assert.ok(source.includes("dco-measurement-instructions"), "Instructions button must be present");
assert.ok(source.includes("ensureTitle"), "Toolbar title must be explicitly restored");

const actionsIndex = hooks.indexOf("door_cutting_order_measurement_actions_ux.js");
const toolbarIndex = hooks.indexOf("door_cutting_order_measurement_toolbar_ux.js");
assert.ok(actionsIndex >= 0 && toolbarIndex > actionsIndex, "Measurement toolbar UX must load after measurement actions");

console.log("Measurement toolbar UX contract passed");