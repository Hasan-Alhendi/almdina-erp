"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const sessionSource = fs.readFileSync(
    path.resolve(
        __dirname,
        "../../public/js/door_cutting_order/costing/door_cutting_order_cost_edit_session_ux.js"
    ),
    "utf8"
);
const pageActionSource = fs.readFileSync(
    path.resolve(
        __dirname,
        "../../public/js/door_cutting_order/core/door_cutting_order_page_edit_action_ux.js"
    ),
    "utf8"
);

const grants = new Set(["view_costs", "approve_special_price"]);
const fakeFrappe = {
    ui: { form: { on() {} } },
    msgprint() {},
};
const fakeWindow = {
    frappe: fakeFrappe,
    cur_frm: null,
    addEventListener() {},
    requestAnimationFrame(callback) {
        if (typeof callback === "function") callback();
        return 1;
    },
    AlmdinaPermissions: {
        canDocument(_frm, capability) {
            return grants.has(capability);
        },
        can(capability) {
            return grants.has(capability);
        },
    },
};

const context = vm.createContext({
    window: fakeWindow,
    frappe: fakeFrappe,
    console,
    Object,
    Array,
    Set,
    Boolean,
    Number,
    String,
    Math,
    Promise,
    __: value => value,
});

vm.runInContext(sessionSource, context, {
    filename: "door_cutting_order_cost_edit_session_ux.js",
});

const api = fakeWindow.AlmdinaCostEditSessionUX;
assert.ok(api, "Cost edit-session API must be installed");

const frm = {
    doctype: "Door Cutting Order",
    doc: {
        name: "DCO-PRICE-WORKSPACE-1",
        docstatus: 0,
        status: "Draft",
        revision_state: "Current",
    },
    is_new() {
        return false;
    },
};

assert.equal(api.canEditCostSettings(frm), false);
assert.equal(api.canEditPiecePrices(frm), true);
assert.equal(
    api.canEditCostWorkspace(frm),
    true,
    "approve_special_price must open the Cost edit session without edit_cost_settings"
);
assert.match(
    pageActionSource,
    /kind === "cost" && typeof api\.canEditCostWorkspace === "function"/,
    "The tab-local Edit button must use workspace authority, not cost-setting authority"
);

frm.doc.status = "Pending Review";
assert.equal(api.canEditPiecePrices(frm), false);
assert.equal(api.canEditCostWorkspace(frm), false);

// Preserve the existing independent cost-settings permission behavior.
grants.add("edit_cost_settings");
assert.equal(api.canEditCostSettings(frm), true);
assert.equal(api.canEditCostWorkspace(frm), true);
assert.equal(api.canEditPiecePrices(frm), false);

grants.delete("edit_cost_settings");
frm.doc.status = "Draft";
grants.delete("approve_special_price");
assert.equal(api.canEditCostWorkspace(frm), false);

grants.add("edit_special_price");
assert.equal(api.canEditPiecePrices(frm), true);
assert.equal(api.canEditCostWorkspace(frm), true);

frm.doc.revision_state = "Superseded";
assert.equal(api.canEditCostWorkspace(frm), false);

console.log("Special price Cost-workspace access simulation passed");
