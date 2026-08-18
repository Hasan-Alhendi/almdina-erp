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
        finally(onFinally) {
            return jqueryThenable(promise.finally(onFinally));
        },
    };
}

async function flushPromises() {
    await Promise.resolve();
    await Promise.resolve();
    await Promise.resolve();
}

function planPayload(orderName, approvedPlan) {
    return {
        order_name: orderName,
        approved_plan: approvedPlan,
        plans: {
            system_draft: {
                name: `${orderName}-SYSTEM`,
                source_type: "System",
                snapshot_json: '{"sheets":[{"source":"System"}]}',
                settings: {
                    packing_mode: "Auto Pro",
                    cutting_machine_type: "Panel Saw",
                    kerf_mm: 4,
                    trim_margin_mm: 5,
                    optimization_time_limit_sec: 20,
                },
                validation: { needs_recalculation: false },
            },
            uploaded_draft: null,
            approved: approvedPlan
                ? {
                    name: approvedPlan,
                    source_type: "System",
                    snapshot_json: '{"sheets":[{"source":"Approved"}]}',
                    settings: {
                        packing_mode: "Auto Pro",
                        cutting_machine_type: "Panel Saw",
                        kerf_mm: 4,
                        trim_margin_mm: 5,
                        optimization_time_limit_sec: 20,
                    },
                    validation: { needs_recalculation: false },
                }
                : null,
        },
    };
}

(async () => {
    const handlers = {};
    const calls = [];
    const listeners = new Map();
    const fakeWindow = {
        cur_frm: null,
        clearTimeout() {},
        requestAnimationFrame() { return 1; },
        addEventListener(name, listener) {
            const current = listeners.get(name) || [];
            current.push(listener);
            listeners.set(name, current);
        },
        dispatchEvent(event) {
            for (const listener of listeners.get(event.type) || []) listener(event);
            return true;
        },
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
        msgprint() {},
        show_alert() {},
    };
    class FakeCustomEvent {
        constructor(type, init = {}) {
            this.type = type;
            this.detail = init.detail;
        }
    }
    const context = vm.createContext({
        window: fakeWindow,
        frappe: fakeFrappe,
        document: {
            // PlanControls only needs to know that its stylesheet already exists;
            // the simulation exercises state/capability behavior, not DOM styling.
            getElementById() { return {}; },
        },
        console,
        Promise,
        Object,
        Array,
        String,
        Number,
        Boolean,
        Set,
        Map,
        CustomEvent: FakeCustomEvent,
        __: value => value,
        setTimeout() {
            return 1;
        },
        requestAnimationFrame() {
            return 1;
        },
    });

    vm.runInContext(source("door_cutting_order/core/door_cutting_order_document_context.js"), context);
    vm.runInContext(source("door_cutting_order/core/door_cutting_order_workspace_store.js"), context);
    vm.runInContext(source("door_cutting_order/cutting_plan/door_cutting_order_plan_workspace_api.js"), context);
    vm.runInContext(source("door_cutting_order/cutting_plan/door_cutting_order_plan_workspace_state.js"), context);
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
        is_new() { return false; },
    };
    fakeWindow.cur_frm = frm;
    fakeWindow.AlmdinaDocumentContext.synchronize(frm);

    // A late response for order A must never populate order B's Plan workspace.
    const stale = fakeWindow.AlmdinaPlanWorkspaceState.load(frm);
    assert.equal(calls[0].options.args.order_name, "DCO-A");
    frm.doc = {
        doctype: "Door Cutting Order",
        name: "DCO-B",
        approved_plan: "PLAN-B",
    };
    fakeWindow.AlmdinaDocumentContext.synchronize(frm);
    calls[0].pending.resolve({ message: planPayload("DCO-A", "PLAN-A") });
    await stale;
    await flushPromises();

    let snapshot = fakeWindow.AlmdinaPlanWorkspaceState.snapshot(frm);
    assert.equal(snapshot.identity, "Door Cutting Order::DCO-B");
    assert.equal(snapshot.data, null);

    const current = fakeWindow.AlmdinaPlanWorkspaceState.load(frm);
    assert.equal(calls[1].options.args.order_name, "DCO-B");
    calls[1].pending.resolve({ message: planPayload("DCO-B", "PLAN-B") });
    await current;
    await flushPromises();
    snapshot = fakeWindow.AlmdinaPlanWorkspaceState.snapshot(frm);
    assert.equal(snapshot.data.order_name, "DCO-B");
    assert.equal(snapshot.data.approved_plan, "PLAN-B");
    assert.equal(snapshot.data.plans.approved.name, "PLAN-B");

    // Regression for the real production state: an immutable approved snapshot
    // may be revised while the order remains at Drawing, but locks after leaving it.
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
    fakeWindow.cur_frm = approvedDrawing;
    fakeWindow.AlmdinaDocumentContext.synchronize(approvedDrawing);

    const drawingLoad = fakeWindow.AlmdinaPlanWorkspaceState.load(approvedDrawing);
    assert.equal(calls[2].options.args.order_name, "DCO-DRAWING");
    calls[2].pending.resolve({ message: planPayload("DCO-DRAWING", "PLAN-APPROVED") });
    await drawingLoad;
    await flushPromises();

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

    console.log("Approved plan workspace navigation and Drawing revision simulation passed");
})().catch(error => {
    console.error(error);
    process.exitCode = 1;
});
