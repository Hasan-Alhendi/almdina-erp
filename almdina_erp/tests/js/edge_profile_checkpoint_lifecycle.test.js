"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = path.resolve(
    __dirname,
    "../../public/js/door_cutting_order/order_entry/edge_banding/door_cutting_order_edge_profile_controls_ux.js"
);
const triggeredFields = [];
const window = {};
const document = {
    createdStyles: new Map(),
    getElementById(id) { return this.createdStyles.get(id) || null; },
    createElement(tag) {
        return { tagName: tag, id: "", textContent: "" };
    },
    head: {
        appendChild(element) {
            document.createdStyles.set(element.id, element);
        },
    },
};
const frappe = {
    utils: { escape_html: value => String(value) },
    ui: {
        form: { on() {} },
    },
};

vm.runInNewContext(fs.readFileSync(source, "utf8"), {
    window,
    document,
    frappe,
    Promise,
    Map,
    Set,
    String,
    Number,
    Boolean,
    Object,
    Array,
    Math,
    setTimeout(callback) {
        callback();
        return 1;
    },
    requestAnimationFrame(callback) {
        callback();
        return 1;
    },
    console,
});

const row = {
    doctype: "Door Cutting Order Detail",
    name: "piece-1",
    edge_long_left: 0,
    edge_long_right: 0,
    edge_width_top: 0,
    edge_width_bottom: 0,
};
const form = {
    doc: { pieces: [row] },
    dirty() {},
    script_manager: {
        trigger(fieldname, doctype, name) {
            triggeredFields.push({ fieldname, doctype, name });
            return Promise.resolve();
        },
    },
};
const tableRow = {
    dataset: { rowName: row.name },
    querySelector() { return null; },
    querySelectorAll() { return []; },
};

window.AlmdinaEdgeProfileControls.applyAllSides(form, tableRow, "Bulk Edge");

assert.deepEqual(
    triggeredFields.map(item => item.fieldname).sort(),
    [
        "edge_long_left",
        "edge_long_left_type_override",
        "edge_long_right",
        "edge_long_right_type_override",
        "edge_width_bottom",
        "edge_width_bottom_type_override",
        "edge_width_top",
        "edge_width_top_type_override",
    ].sort(),
    "Bulk edge changes must run Frappe child-field lifecycle hooks for checkpoint capture"
);
assert.ok(triggeredFields.every(item => (
    item.doctype === row.doctype && item.name === row.name
)));
assert.equal(row.edge_long_left_type_override, "Bulk Edge");
assert.equal(row.edge_long_right_type_override, "Bulk Edge");
assert.equal(row.edge_width_top_type_override, "Bulk Edge");
assert.equal(row.edge_width_bottom_type_override, "Bulk Edge");

console.log("Bulk edge profile checkpoint lifecycle passed");
