"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "../..");
const measurements = "public/js/door_cutting_order/order_entry/measurements";
const toolbarSource = fs.readFileSync(
    path.join(root, measurements, "door_cutting_order_measurement_toolbar_ux.js"),
    "utf8"
);
const actionsSource = fs.readFileSync(
    path.join(root, measurements, "door_cutting_order_measurement_actions_ux.js"),
    "utf8"
);
const assets = fs.readFileSync(path.join(root, "frontend_assets.py"), "utf8");

assert.doesNotThrow(() => new Function(toolbarSource), "Measurement toolbar UX must remain valid JavaScript");
assert.doesNotThrow(() => new Function(actionsSource), "Measurement actions UX must remain valid JavaScript");
for (const marker of [
    "جدول قياسات الدرف",
    "dco-measurement-instructions",
    "تعليمات جدول القياسات",
]) {
    assert.ok(toolbarSource.includes(marker), `Missing toolbar marker: ${marker}`);
}
for (const marker of ["dco-print-measurements", "dco-open-measurements-window"]) {
    assert.ok(actionsSource.includes(marker), `Missing measurement action marker: ${marker}`);
}
assert.ok(toolbarSource.includes("ensureTitle"), "Toolbar title must be explicitly restored");

const actionsIndex = assets.indexOf("door_cutting_order_measurement_actions_ux.js");
const toolbarIndex = assets.indexOf("door_cutting_order_measurement_toolbar_ux.js");
assert.ok(actionsIndex >= 0 && toolbarIndex > actionsIndex, "Measurement toolbar UX must load after measurement actions");

console.log("Measurement toolbar UX contract passed");
