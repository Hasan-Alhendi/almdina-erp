"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

function source(relativePath) {
    return fs.readFileSync(path.resolve(__dirname, "../../", relativePath), "utf8");
}

const previewEditSource = source(
    "public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_preview_edit_ux.js"
);
const editCoordinatorSource = source(
    "public/js/door_cutting_order/core/door_cutting_order_edit_session_coordinator.js"
);

async function validatePostCommitCostReconciliation() {
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

    vm.runInContext(previewEditSource, context, {
        filename: "door_cutting_order_plan_preview_edit_ux.js",
    });

    const ux = fakeWindow.AlmdinaPlanPreviewEditUX;
    assert.ok(ux);
    assert.equal(typeof ux.refreshCommittedWorkspaces, "function");

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
}

async function validateCoordinatorCommitsDisplayedPreview() {
    let workspaceEditing = false;
    let baseSaveCalls = 0;
    let baseCancelCalls = 0;
    let commitCalls = 0;
    let previewResets = 0;
    let invalidations = 0;
    let refreshes = 0;

    const frm = {
        doctype: "Door Cutting Order",
        doc: { doctype: "Door Cutting Order", name: "DCO-PREVIEW-SAVE" },
        fields_dict: {},
        trigger() {},
    };

    const fakeWindow = {
        cur_frm: frm,
        requestAnimationFrame(callback) { callback(); return 1; },
        addEventListener() {},
    };
    fakeWindow.window = fakeWindow;

    const frappe = {
        ui: { form: { on() {} } },
        msgprint() {},
        show_alert() {},
    };

    const context = vm.createContext({
        window: fakeWindow,
        frappe,
        console,
        Object,
        String,
        Number,
        Boolean,
        Array,
        Promise,
        Set,
        WeakMap,
        Map,
        __: value => String(value),
    });

    vm.runInContext(editCoordinatorSource, context, {
        filename: "door_cutting_order_edit_session_coordinator.js",
    });

    const coordinator = fakeWindow.AlmdinaDcoEditSessionCoordinator;
    assert.ok(coordinator);
    assert.equal(typeof coordinator.decorate, "function");

    coordinator.register("plan", {
        canStart() { return true; },
        start() {
            workspaceEditing = true;
            return true;
        },
        save() {
            baseSaveCalls += 1;
            return true;
        },
        cancel() {
            baseCancelCalls += 1;
            workspaceEditing = false;
            return true;
        },
    });

    fakeWindow.AlmdinaPlanEditSessionUX = Object.freeze({
        isEditing() { return workspaceEditing; },
        startEditing(target) { return coordinator.start(target, "plan"); },
        saveEditing(target) { return coordinator.save(target, "plan"); },
        cancelEditing(target) { return coordinator.cancel(target, "plan"); },
    });

    fakeWindow.AlmdinaPlanPreviewSession = {
        reset() { previewResets += 1; },
        snapshot() {
            return {
                status: "ready",
                payload: { plan: { sheets: [{ id: "preview-sheet" }] } },
            };
        },
        isCommittable() { return true; },
        isBusy() { return false; },
        async commit() {
            commitCalls += 1;
            return { exact_preview_commit: true };
        },
    };

    fakeWindow.AlmdinaWorkspaceSyncCoordinator = {
        invalidate(_target, resources, reason) {
            invalidations += 1;
            assert.deepEqual(Array.from(resources), ["plan", "cost"]);
            assert.equal(reason, "plan_changed");
        },
        async refresh(_target, resources, options) {
            refreshes += 1;
            assert.deepEqual(Array.from(resources), ["plan", "cost"]);
            assert.equal(options.force, true);
            assert.equal(options.reason, "plan_changed");
        },
    };

    fakeWindow.AlmdinaPlanWorkspacePresenterAdapter = { project() {} };
    fakeWindow.AlmdinaPlanPreviewPresenter = {
        renderActionMessage() {},
        renderPreviewPlan() {},
        renderPersistedEditingState() {},
        restorePersistedPresentation() {},
    };

    vm.runInContext(previewEditSource, context, {
        filename: "door_cutting_order_plan_preview_edit_ux.js",
    });

    assert.equal(await coordinator.start(frm, "plan"), true);
    assert.equal(workspaceEditing, true);
    assert.equal(coordinator.snapshot(frm).phase, "editing");

    assert.equal(await coordinator.save(frm, "plan"), true);
    assert.equal(commitCalls, 1, "coordinator Save must commit the exact displayed preview");
    assert.equal(baseSaveCalls, 0, "legacy settings-only Save must not run after preview decoration");
    assert.equal(baseCancelCalls, 1, "post-commit cleanup must use the raw base cancel exactly once");
    assert.equal(workspaceEditing, false, "the Plan workspace edit projection must close with the commit");
    assert.equal(coordinator.snapshot(frm).phase, "idle");
    assert.equal(coordinator.snapshot(frm).activeKind, null);
    assert.equal(invalidations, 1);
    assert.equal(refreshes, 1);
    assert.ok(previewResets >= 1, "a fresh edit session must clear any previous preview");
}

(async () => {
    await validatePostCommitCostReconciliation();
    await validateCoordinatorCommitsDisplayedPreview();
    console.log("Plan preview save and Cost reconciliation simulations passed");
})().catch((error) => {
    console.error(error);
    process.exitCode = 1;
});
