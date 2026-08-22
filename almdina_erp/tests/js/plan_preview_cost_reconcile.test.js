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
const alerts = [];
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
    msgprint() {},
    show_alert(options, seconds) {
        alerts.push({ options: { ...options }, seconds });
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

    // A committed plan is durable before workspace reconciliation. A transient
    // Cost refresh failure must therefore produce a recoverable warning, not make
    // saveEditing report that the mutation itself failed.
    calls.length = 0;
    alerts.length = 0;
    fakeWindow.AlmdinaPlanPreviewSession = {
        isCommittable() { return true; },
        isBusy() { return false; },
        async commit() {
            calls.push(["commit"]);
            return true;
        },
    };
    fakeWindow.AlmdinaWorkspaceSyncCoordinator.refresh = async (_frm, resources, options) => {
        calls.push(["refresh", Array.from(resources), { ...options }]);
        throw new Error("simulated cost refresh failure");
    };

    const saved = await fakeWindow.AlmdinaPlanEditSessionUX.saveEditing(frm);
    assert.equal(saved, true, "a post-commit refresh failure must not turn a durable commit into failure");
    assert.deepEqual(calls.slice(0, 3), [
        ["commit"],
        ["invalidate", ["plan", "cost"], "plan_changed"],
        ["refresh", ["plan", "cost"], { force: true, reason: "plan_changed" }],
    ]);
    assert.equal(alerts.length, 1);
    assert.equal(alerts[0].options.indicator, "orange");
    assert.match(alerts[0].options.message, /تم حفظ خطة المعاينة بنجاح/);

    console.log("Plan preview Cost reconciliation simulation passed");
})().catch((error) => {
    console.error(error);
    process.exitCode = 1;
});
