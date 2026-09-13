"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

function source(relativePath) {
    return fs.readFileSync(path.resolve(__dirname, "../../", relativePath), "utf8");
}

async function run() {
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
        Promise,
        Set,
        WeakMap,
        Map,
        CustomEvent: class CustomEvent {},
        __: value => String(value),
    });

    vm.runInContext(
        source("public/js/door_cutting_order/core/door_cutting_order_edit_session_coordinator.js"),
        context,
        { filename: "door_cutting_order_edit_session_coordinator.js" }
    );

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

    vm.runInContext(
        source("public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_preview_edit_ux.js"),
        context,
        { filename: "door_cutting_order_plan_preview_edit_ux.js" }
    );

    assert.equal(await coordinator.start(frm, "plan"), true);
    assert.equal(workspaceEditing, true);
    assert.equal(coordinator.snapshot(frm).phase, "editing");

    assert.equal(await coordinator.save(frm, "plan"), true);
    assert.equal(commitCalls, 1, "toolbar/coordinator save must commit the displayed preview");
    assert.equal(baseSaveCalls, 0, "legacy settings-only save must never run after preview decoration");
    assert.equal(baseCancelCalls, 1, "post-commit cleanup must use the raw base cancel exactly once");
    assert.equal(workspaceEditing, false, "the Plan workspace edit projection must close with the commit");
    assert.equal(coordinator.snapshot(frm).phase, "idle");
    assert.equal(coordinator.snapshot(frm).activeKind, null);
    assert.equal(invalidations, 1);
    assert.equal(refreshes, 1);
    assert.ok(previewResets >= 1, "starting a fresh edit session must clear any previous preview");

    console.log("Plan preview coordinator save regression passed");
}

run().catch((error) => {
    console.error(error);
    process.exitCode = 1;
});
