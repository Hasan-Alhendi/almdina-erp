"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(
    path.resolve(__dirname, "../../public/js/door_cutting_order_plan_tabs_ux.js"),
    "utf8"
);

const grants = new Set(["view_cutting_plan"]);
const fakeWindow = {
    AlmdinaPermissions: {
        canDocument(_frm, capability) {
            return grants.has(capability);
        },
        can(capability) {
            return grants.has(capability);
        },
    },
    AlmdinaCuttingPlanRender: {
        print(_frm, plan) {
            fakeWindow.printedPlan = plan;
        },
    },
};
const fakeFrappe = {
    ui: { form: { on() {} } },
    call() {
        return Promise.resolve({ message: {} });
    },
};
const context = vm.createContext({
    window: fakeWindow,
    frappe: fakeFrappe,
    console,
    Promise,
    Object,
    Array,
    Boolean,
    String,
    Set,
    __: value => value,
    setTimeout() {},
});

vm.runInContext(source, context, {
    filename: "door_cutting_order_plan_tabs_ux.js",
});

const frm = { doc: { name: "DCO-TEST" } };
assert.deepEqual(
    [...fakeWindow.AlmdinaPlanTabsUX.visibleTabs(frm)].map(tab => tab.id),
    [],
    "an umbrella grant must not override explicit granular denials in the browser"
);

grants.add("view_system_cutting_plan");
assert.deepEqual(
    [...fakeWindow.AlmdinaPlanTabsUX.visibleTabs(frm)].map(tab => tab.id),
    ["System"]
);

grants.add("view_approved_cutting_plan");
assert.deepEqual(
    [...fakeWindow.AlmdinaPlanTabsUX.visibleTabs(frm)].map(tab => tab.id),
    ["System", "Approved"]
);

grants.add("view_uploaded_cutting_plan");
frm.doc.custom_plan_json = JSON.stringify({ sheets: [{ source: "Custom" }] });
frm.__almdina_active_plan_tab = "Custom";
fakeWindow.AlmdinaPlanTabsUX.printActivePlan(frm);
assert.equal(fakeWindow.printedPlan.sheets[0].source, "Custom");

console.log("Granular cutting-plan tab capability contract passed");
