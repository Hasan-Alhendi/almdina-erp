"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.resolve(__dirname, "../..");

function read(relative) {
    return fs.readFileSync(path.join(root, "public/js/door_cutting_order", relative), "utf8");
}

function element() {
    return {
        nodeType: 1,
        style: {},
        children: [],
        appendChild() {},
        setAttribute() {},
        addEventListener() {},
    };
}

const context = {
    console,
    document: { createElement: element, getElementById: () => null, head: element() },
    window: {},
    addEventListener() {},
    requestAnimationFrame(callback) { callback(); },
    frappe: { ui: { form: { on() {} } }, utils: { escape_html: (value) => String(value) } },
    __: (value) => value,
};
context.window = context;
vm.createContext(context);
vm.runInContext(read("cutting_plan/door_cutting_order_plan_workspace_presenter_adapter.js"), context);
vm.runInContext(read("cutting_plan/door_cutting_order_plan_settings_summary_ux.js"), context);

const operational = {
    deduct_edge_thickness: 0,
    kerf_mm: 3,
    liner_tool_diameter_mm: 6,
};
const custom = {
    name: "CP-CUSTOM",
    source_type: "Uploaded DXF",
    settings: { deduct_edge_thickness: 1, kerf_mm: 4, liner_tool_diameter_mm: 8 },
};
const approved = {
    name: "CP-APPROVED",
    source_type: "System",
    status: "Approved",
    settings: { deduct_edge_thickness: 1, kerf_mm: 5 },
};
const system = {
    name: "CP-SYSTEM",
    source_type: "System",
    status: "Draft",
    settings: { ...operational },
};
let displayed = custom;
const frm = { doctype: "Door Cutting Order", doc: { name: "DCO-1", doctype: "Door Cutting Order" } };
const saves = [];
context.frappe.call = (options) => {
    saves.push(options);
    return Promise.resolve({});
};
context.AlmdinaPlanWorkspaceState = {
    snapshot() {
        return {
            status: "ready",
            identity: "Door Cutting Order::DCO-1",
            data: {
                order_name: "DCO-1",
                calculation_settings: operational,
                editable_settings: operational,
            },
        };
    },
    displayedPlan() { return displayed; },
    planForTab(_frm, tab) {
        if (tab === "System") return system;
        if (tab === "Custom") return custom;
        if (tab === "Approved") return approved;
        return null;
    },
};

const summary = context.AlmdinaPlanSettingsSummaryUX;
const adapter = context.AlmdinaPlanWorkspacePresenterAdapter;

for (const row of [custom, approved, system]) {
    displayed = row;
    assert.equal(summary.displayedSettings(frm).deduct_edge_thickness, 0);
    assert.equal(adapter.activeSettings(frm).deduct_edge_thickness, 0);
}

assert.equal(custom.settings.deduct_edge_thickness, 1);
assert.equal(approved.settings.deduct_edge_thickness, 1);
assert.equal(summary.displayedSettings(frm).liner_tool_diameter_mm, 6);
displayed = custom;
assert.equal(summary.displayedSettings(frm).liner_tool_diameter_mm, 8);
assert.equal(saves.length, 0);

displayed = custom;
context.AlmdinaPlanWorkspaceState.snapshot = () => ({
    status: "ready",
    identity: "Door Cutting Order::DCO-1",
    data: { order_name: "DCO-1" },
});
assert.equal(adapter.activeSettings(frm).deduct_edge_thickness, 0);
assert.equal(summary.displayedSettings(frm).deduct_edge_thickness, 0);

console.log("plan deduct tab stability tests passed");
