"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(
    path.resolve(
        __dirname,
        "../../public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_preview_edit_ux.js"
    ),
    "utf8"
);

const calls = [];
const formHandlers = [];
const listeners = [];
let projected = 0;

const frm = {
    doctype: "Door Cutting Order",
    doc: { name: "DCO-1" },
};

const fakeWindow = {
    cur_frm: frm,
    AlmdinaPlanEditSessionUX: {
        isEditing() { return false; },
        startEditing() { return true; },
        cancelEditing() { return true; },
    },
    AlmdinaWorkspaceSyncCoordinator: {
        invalidate(_frm, resources, reason) {
            calls.push(["invalidate", Array.from(resources), reason]);
        },
        async refresh(_frm, resources, options) {
            calls.push(["refresh", Array.from(resources), { ...options }]);
        },
    },
    AlmdinaPlanWorkspacePresenterAdapter: {
        project() { projected += 1; },
    },
    addEventListener(name) { listeners.push(name); },
    requestAnimationFrame(callback) { callback(); },
};

const fakeFrappe = {
    ui: {
        form: {
            on(doctype, mapping) { formHandlers.push([doctype, mapping]); },
        },
    },
};

const context = vm.createContext({
    window: fakeWindow,
    frappe: fakeFrappe,
    console,
    Object,
    String,
    Boolean,
    Array,
    Promise,
    __: value => value,
});

vm.runInContext(source, context, {
    filename: "door_cutting_order_plan_preview_edit_ux.js",
});

const ux = fakeWindow.AlmdinaPlanPreviewEditUX;
assert.ok(ux);
assert.equal(typeof ux.refreshCommittedWorkspaces, "function");

(async () => {
    assert.equal(await ux.refreshCommittedWorkspaces(frm), true);
    assert.deepEqual(calls, [
        ["invalidate", ["plan", "cost"], "plan_changed"],
        ["refresh", ["plan", "cost"], { force: true, reason: "plan_changed" }],
    ]);
    assert.equal(projected, 1);
    assert.ok(listeners.includes("almdina:plan-preview-updated"));

    console.log("Plan preview Cost reconciliation simulation passed");
})().catch((error) => {
    console.error(error);
    process.exitCode = 1;
});
