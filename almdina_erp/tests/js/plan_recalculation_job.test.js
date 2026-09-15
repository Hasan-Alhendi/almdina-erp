"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const jobSource = fs.readFileSync(
    path.resolve(
        __dirname,
        "../../public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_recalculation_job.js"
    ),
    "utf8"
);
const policySource = fs.readFileSync(
    path.resolve(
        __dirname,
        "../../public/js/door_cutting_order/order_entry/door_cutting_order_mutation_impact_policy.js"
    ),
    "utf8"
);

const calls = [];
const handlers = new Map();
let permissions = { recalculate_plan: true };

const frm = {
    doctype: "Door Cutting Order",
    doc: { name: "DCO-1", doctype: "Door Cutting Order" },
    is_new() { return false; },
};

const fakeFrappe = {
    call(options) {
        calls.push({ method: options.method, freeze: options.freeze, args: options.args });
        return Promise.resolve({
            message: { queued: true, status: "queued", generation: 1, reason: "stale" },
        });
    },
    ui: {
        form: {
            on(doctype, mapping) {
                handlers.set(doctype, Object.assign(handlers.get(doctype) || {}, mapping));
            },
        },
    },
    realtime: { on() {}, off() {} },
};

const windowObject = {
    AlmdinaPermissions: {
        canDocument(_frm, capability) {
            return Boolean(permissions[capability]);
        },
    },
    AlmdinaDocumentContext: {
        capture() { return { identity: "Door Cutting Order::DCO-1", generation: 1 }; },
        isCurrent() { return true; },
        registerCleanup() { return true; },
        cancelEffect() { return true; },
        schedule() { return 1; },
    },
    AlmdinaWorkspaceSyncCoordinator: {
        invalidate() { return ["cost"]; },
        async refresh() { return ["plan", "cost"]; },
    },
    dispatchEvent() {},
    addEventListener() {},
};
windowObject.window = windowObject;

const context = vm.createContext({
    window: windowObject,
    frappe: fakeFrappe,
    console,
    Set,
    Map,
    Object,
    String,
    Boolean,
    Number,
    Array,
    Date,
    Promise,
    CustomEvent: class CustomEvent {
        constructor(type, init) {
            this.type = type;
            this.detail = init && init.detail;
        }
    },
});

vm.runInContext(jobSource, context, { filename: "door_cutting_order_plan_recalculation_job.js" });
vm.runInContext(policySource, context, { filename: "door_cutting_order_mutation_impact_policy.js" });

const job = context.window.AlmdinaPlanRecalculationJob;
const policy = context.window.AlmdinaOrderMutationImpactPolicy;

assert.ok(job);
assert.equal(job.shouldEnqueueAfterSave(frm, { resources: ["plan", "cost"] }), true);
assert.equal(
    job.shouldEnqueueAfterSave(
        { ...frm, __almdina_preserve_edit_session_after_save: true },
        { resources: ["plan", "cost"] }
    ),
    false,
    "checkpoint saves must not enqueue background recalc"
);
assert.equal(
    job.shouldEnqueueAfterSave(frm, { resources: ["cost"] }),
    false,
    "extra-addon-only saves must not enqueue the optimizer"
);

permissions.recalculate_plan = false;
assert.equal(job.shouldEnqueueAfterSave(frm, { resources: ["plan"] }), false);
permissions.recalculate_plan = true;

const older = job.applyState(frm, { status: "queued", generation: 4 }, { force: true });
assert.equal(older.generation, 4);
const ignored = job.applyState(frm, { status: "completed", generation: 2 });
assert.equal(ignored.status, "queued", "older realtime completions must not clobber a newer generation");
assert.equal(ignored.generation, 4);

(async () => {
    frm.__almdinaWorkspaceMutationImpact = {
        resources: ["plan", "cost"],
        reasons: ["order_inputs_changed"],
    };
    await policy.reconcileAfterSave(frm);
    assert.equal(calls.length, 1);
    assert.equal(calls[0].method, job.ENQUEUE_METHOD);
    assert.equal(calls[0].freeze, false);
    assert.equal(calls[0].args.order_name, "DCO-1");

    calls.length = 0;
    frm.__almdina_preserve_edit_session_after_save = true;
    frm.__almdinaWorkspaceMutationImpact = {
        resources: ["plan", "cost"],
        reasons: ["order_inputs_changed"],
    };
    await policy.reconcileAfterSave(frm);
    assert.equal(calls.length, 0, "checkpoint after_save must not call enqueue");

    console.log("Background plan recalculation job simulation passed");
})().catch((error) => {
    console.error(error);
    process.exitCode = 1;
});
