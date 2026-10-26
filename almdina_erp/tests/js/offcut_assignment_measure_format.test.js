"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(
    path.resolve(
        __dirname,
        "../../public/js/door_cutting_order/costing/door_cutting_order_cost_offcut_assignment_ux.js"
    ),
    "utf8"
);

const fakeWindow = {};
const context = vm.createContext({
    window: fakeWindow,
    frappe: { utils: { escape_html: (value) => String(value) } },
    console,
    Object,
    Array,
    String,
    Number,
    Boolean,
    Math,
});
vm.runInContext(source, context, {
    filename: "door_cutting_order_cost_offcut_assignment_ux.js",
});

const api = fakeWindow.AlmdinaCostOffcutAssignmentUX;
assert.ok(api);
assert.equal(typeof api.formatMeasureNumber, "function");
assert.equal(typeof api.formatMeasureText, "function");
assert.equal(typeof api.rowLabel, "function");

assert.equal(api.formatMeasureNumber(59.299999999999926), "59.3");
assert.equal(api.formatMeasureNumber(61.799999999999905), "61.8");
assert.equal(api.formatMeasureNumber(63.800000000000004), "63.8");
assert.equal(api.formatMeasureNumber(39.8), "39.8");
assert.equal(api.formatMeasureNumber(60.0), "60");
assert.equal(api.formatMeasureNumber("60.00"), "60");
assert.equal(api.formatMeasureNumber(42.25), "42.25");
assert.equal(api.formatMeasureNumber(""), null);
assert.equal(api.formatMeasureNumber(null), null);
assert.equal(api.formatMeasureNumber(undefined), null);
assert.equal(api.formatMeasureNumber("not-a-number"), null);

assert.equal(
    api.formatMeasureText("59.299999999999926 × 61.799999999999905 سم"),
    "59.3 × 61.8 سم"
);
assert.equal(
    api.formatMeasureText("63.800000000000004 × 61.799999999999905 cm"),
    "63.8 × 61.8 cm"
);

assert.equal(
    api.rowLabel({
        piece_number: 3,
        measurement: "59.299999999999926 × 61.799999999999905 سم",
        width: 59.299999999999926,
        length: 61.799999999999905,
    }).measure,
    "59.3 × 61.8 سم"
);
assert.equal(
    api.rowLabel({
        piece_label: "2.1",
        size: "39.8 × 60.00 سم",
    }).measure,
    "39.8 × 60 سم"
);
assert.equal(
    api.rowLabel({
        piece_number: 1,
        width: 42.25,
        length: 60,
    }).measure,
    "42.25 × 60 cm"
);
assert.equal(
    api.rowLabel({
        piece_number: 1,
        width: "bad",
        length: 60,
    }).measure,
    "—"
);

console.log("OFFCUT assignment measure formatting passed");
