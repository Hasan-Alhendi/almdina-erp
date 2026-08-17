"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

function source(filename) {
    return fs.readFileSync(path.resolve(__dirname, "../../public/js", filename), "utf8");
}

function deferred() {
    let resolve;
    let reject;
    const promise = new Promise((resolvePromise, rejectPromise) => {
        resolve = resolvePromise;
        reject = rejectPromise;
    });
    return { promise, resolve, reject };
}

function jqueryThenable(promise) {
    return {
        then(onFulfilled, onRejected) {
            return jqueryThenable(promise.then(onFulfilled, onRejected));
        },
        catch(onRejected) {
            return jqueryThenable(promise.catch(onRejected));
        },
    };
}

async function flushPromises() {
    await Promise.resolve();
    await Promise.resolve();
    await Promise.resolve();
}

(async () => {
    const handlers = {};
    const calls = [];
    const fakeWindow = {
        cur_frm: null,
        clearTimeout() {},
        requestAnimationFrame() { return 1; },
        addEventListener() {},
        AlmdinaPermissions: {
            canDocument() {
                return true;
            },
            can() {
                return true;
            },
        },
    };
    const fakeFrappe = {
        ui: {
            form: {
                on(doctype, events) {
                    handlers[doctype] = handlers[doctype] || {};
                    Object.assign(handlers[doctype], events);
                },
            },
        },
        call(options) {
            const pending = deferred();
            calls.push({ options, pending });
            return jqueryThenable(pending.promise);
        },
        utils: { escape_html: value => String(value) },
    };
    const context = vm.createContext({
        window: fakeWindow,
        frappe: fakeFrappe,
        console,
        Promise,
        Object,
        Array,
        String,
        Number,
        Boolean,
        Set,
        Map,
        __: value => value,
        setTimeout() {
            return 1;
        },
    });
    vm.runInContext(source("door_cutting_order/core/door_cutting_order_document_context.js"), context);
    vm.runInContext(source("door_cutting_order/cutting_plan/door_cutting_order_plan_tabs_ux.js"), context);
    vm.runInContext(source("door_cutting_order/cutting_plan/door_cutting_order_plan_controls_ux.js"), context);
    vm.runInContext(source("door_cutting_order/cutting_plan/door_cutting_order_plan_edit_session_ux.js"), context);

    const frm = {
        doctype: "Door Cutting Order",
        doc: {
            doctype: "Door Cutting Order",
            name: "DCO-A",
            approved_plan: "PLAN-A",
        },
        fields_dict: {},
    };
    fakeWindow.cur_frm = frm;
    fakeWindow.AlmdinaDocumentContext.synchronize(frm);

    const stale = fakeWindow.AlmdinaPlanTabsUX.ensureApprovedPlanLoaded(frm);
    assert.equal(calls[0].options.args.order_name, "DCO-A");
    frm.doc = {
        doctype: "Door Cutting Order",
        name: "DCO-B",
        approved_plan: "PLAN-B",
    };
    fakeWindow.AlmdinaDocumentContext.synchronize(frm);
    calls[0].pending.resolve({ message: { snapshot_json: '{"sheets":[{"source":"A"}]}' } });
    assert.equal(await stale, null);
    assert.equal(frm.__almdina_approved_plan_snapshot, null);

    const current = fakeWindow.AlmdinaPlanTabsUX.ensureApprovedPlanLoaded(frm);
    assert.equal(calls[1].options.args.order_name, "DCO-B");
    calls[1].pending.resolve({ message: { snapshot_json: '{"sheets":[{"source":"B"}]}' } });
    await current;
    await flushPromises();
    assert.equal(frm.__almdina_approved_plan_order, "DCO-B");
    assert.equal(frm.__almdina_approved_plan_snapshot.sheets[0].source, "B");

    // Regression for the real production state: an immutable approved snapshot
    // does not permanently lock the optimizer while the order is still at Drawing.
    const approvedDrawing = {
        doctype: "Door Cutting Order",
        doc: {
            doctype: "Door Cutting Order",
            name: "DCO-DRAWING",
            status: "At Drawing",
            docstatus: 0,
            revision_state: "Current",
            approved_plan: "PLAN-APPROVED",
            production_path: "ROUTE-1",
            current_production_stage: "STAGE-DRAWING",
        },
        fields_dict: {},
        is_new() { return false; },
        __almdina_stage_context_ready: true,
        __almdina_stage_context_key: "STAGE-DRAWING",
        __almdina_stage_type: "Drawing",
        __almdina_actor_holds_stage_role: true,
    };

    assert.equal(
        fakeWindow.AlmdinaPlanEditSessionUX.canEditPlanSettings(approvedDrawing),
        true,
        "approved plan settings must remain editable at Drawing with edit_optimizer_settings"
    );
    assert.equal(
        fakeWindow.AlmdinaPlanControlsUX.canCalculate(approvedDrawing),
        true,
        "approved plan may be recalculated at Drawing when the actor also holds stage access"
    );

    approvedDrawing.doc.status = "At CNC";
    approvedDrawing.doc.current_production_stage = "STAGE-CNC";
    approvedDrawing.__almdina_stage_context_key = "STAGE-CNC";
    approvedDrawing.__almdina_stage_type = "CNC";
    assert.equal(
        fakeWindow.AlmdinaPlanEditSessionUX.canEditPlanSettings(approvedDrawing),
        false,
        "approved plan must become locked after leaving Drawing"
    );
    assert.equal(
        fakeWindow.AlmdinaPlanControlsUX.canCalculate(approvedDrawing),
        false,
        "approved plan recalculation must remain locked at CNC"
    );

    console.log("Approved cutting-plan navigation and Drawing revision simulation passed");
})().catch(error => {
    console.error(error);
    process.exitCode = 1;
});
