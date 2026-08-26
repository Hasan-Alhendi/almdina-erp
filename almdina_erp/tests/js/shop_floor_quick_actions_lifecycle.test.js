"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

const source = fs.readFileSync(
    "almdina_erp/public/js/shop_floor_quick_actions.js",
    "utf8"
);

function deferred() {
    let resolve;
    let reject;
    const promise = new Promise((resolvePromise, rejectPromise) => {
        resolve = resolvePromise;
        reject = rejectPromise;
    });
    return { promise, resolve, reject };
}

const calls = [];
const alerts = [];
const messages = [];
const confirms = [];
const dialogs = [];
const owned = [];
let current = true;
let staleMutationSuccesses = 0;
let uiSuccesses = 0;
let uiErrors = 0;

const button = {
    disabled: false,
    attributes: {},
    classList: { toggle() {} },
    setAttribute(name, value) { this.attributes[name] = value; },
};

class FakeDialog {
    constructor(config) {
        this.config = config;
        this.hidden = 0;
        this.fields_dict = { next_assignee_dropdown: {} };
        dialogs.push(this);
    }

    show() {}

    hide() { this.hidden += 1; }
}

function surface() {
    return { hidden: 0, hide() { this.hidden += 1; } };
}

const context = {
    console,
    Promise,
    __(value) { return value; },
    frappe: {
        ui: { Dialog: FakeDialog },
        call(options) {
            const request = deferred();
            calls.push({ options, request });
            return request.promise;
        },
        confirm(message, yes) {
            const child = surface();
            confirms.push({ message, yes, child });
            return child;
        },
        show_alert(payload) { alerts.push(payload); },
        msgprint(payload) {
            const child = surface();
            messages.push({ payload, child });
            return child;
        },
    },
    window: {},
};
context.window.window = context.window;
vm.createContext(context);
vm.runInContext(source, context, { filename: "shop_floor_quick_actions.js" });

const lifecycle = {
    isCurrent: () => current,
    ownTransient(child, key) {
        owned.push({ child, key });
        return child;
    },
    onStaleMutationSuccess() {
        staleMutationSuccesses += 1;
    },
};

function options() {
    return {
        button,
        lifecycle,
        onSuccess() { uiSuccesses += 1; },
        onError() { uiErrors += 1; },
    };
}

function request(suffix, occurrence = 0) {
    const matches = calls.filter(call => call.options.method.endsWith(suffix));
    assert.ok(matches[occurrence], `missing ${suffix} request ${occurrence}`);
    return matches[occurrence].request;
}

async function flush() {
    await Promise.resolve();
    await new Promise(resolve => setImmediate(resolve));
}

(async () => {
    const api = context.window.AlmdinaShopFloorQuickActions;

    // A caller-owned generation invalidates the stage guard read itself.
    const staleGuard = api.perform(
        { order: "DCO-STALE-GUARD", stage: "PST-1", canStart: true },
        options()
    );
    current = false;
    request("get_current_stage_context", 0).resolve({
        message: { actor_holds_operational_role: true, can_start_stage: true },
    });
    await staleGuard;
    assert.equal(calls.filter(call => call.options.method.endsWith("start_my_stage")).length, 0);
    assert.equal(messages.length, 0, "a stale guard read must not emit a message");

    // Handoff context is a read and cannot open a worker/no-workers child after hide.
    current = true;
    const staleHandoff = api.perform(
        { order: "DCO-STALE-HANDOFF", stage: "PST-2", canHandoff: true },
        options()
    );
    request("get_current_stage_context", 1).resolve({
        message: { actor_holds_operational_role: true, can_handoff_stage: true },
    });
    await flush();
    current = false;
    request("get_handoff_context", 0).resolve({
        message: {
            final_stage: false,
            workers: [{ name: "worker@example.com" }],
            next_department: "CNC",
        },
    });
    await staleHandoff;
    assert.equal(dialogs.length, 0, "stale handoff context cannot open a worker dialog");
    assert.equal(messages.length, 0);

    // The mutation still succeeds, while its PAGE UI completion is suppressed.
    current = true;
    button.disabled = false;
    const mutation = api.perform(
        { order: "DCO-MUTATION", stage: "PST-3", canStart: true },
        options()
    );
    request("get_current_stage_context", 2).resolve({
        message: { actor_holds_operational_role: true, can_start_stage: true },
    });
    await flush();
    const startMutation = request("start_my_stage", 0);
    assert.equal(button.disabled, true);
    current = false;
    startMutation.resolve({ message: { ok: true } });
    const mutationResult = await mutation;
    assert.deepEqual(JSON.parse(JSON.stringify(mutationResult)), { ok: true });
    assert.equal(alerts.length, 0, "hidden mutation success must not alert");
    assert.equal(uiSuccesses, 0, "hidden mutation success must not call the UI callback");
    assert.equal(staleMutationSuccesses, 1, "the caller must be told to reconcile fresh state");
    assert.equal(button.disabled, true, "stale completion must not touch the hidden button DOM");

    // Final confirmation is parent-owned and its stale callback cannot start a mutation.
    current = true;
    button.disabled = false;
    const finalAction = api.perform(
        { order: "DCO-FINAL", stage: "PST-FINAL", canHandoff: true },
        options()
    );
    request("get_current_stage_context", 3).resolve({
        message: { actor_holds_operational_role: true, can_handoff_stage: true },
    });
    await flush();
    request("get_handoff_context", 1).resolve({ message: { final_stage: true, workers: [] } });
    await finalAction;
    assert.equal(confirms.length, 1);
    assert.ok(owned.some(item => item.key === "terminal-confirm"));
    current = false;
    confirms[0].yes();
    await flush();
    assert.equal(
        calls.filter(call => call.options.method.endsWith("handoff_to_next")).length,
        0,
        "a stale confirmation callback cannot start a mutation"
    );

    // Worker dialog ownership is also supplied by the caller, with stale submit blocked.
    current = true;
    const workerAction = api.perform(
        { order: "DCO-WORKER", stage: "PST-WORKER", canHandoff: true },
        options()
    );
    request("get_current_stage_context", 4).resolve({
        message: { actor_holds_operational_role: true, can_handoff_stage: true },
    });
    await flush();
    request("get_handoff_context", 2).resolve({
        message: {
            final_stage: false,
            workers: [{ name: "worker@example.com", full_name: "Worker" }],
            next_department: "CNC",
        },
    });
    await workerAction;
    assert.equal(dialogs.length, 1);
    assert.ok(owned.some(item => item.key === "worker-dialog"));
    current = false;
    dialogs[0].config.primary_action();
    assert.equal(dialogs[0].hidden, 1);
    assert.equal(
        calls.filter(call => call.options.method.endsWith("handoff_to_next")).length,
        0,
        "a stale worker-dialog submit cannot start a mutation"
    );
    assert.equal(uiErrors, 0);

    console.log("Shop Floor caller-owned quick-action lifecycle simulation passed");
})().catch(error => {
    console.error(error);
    process.exitCode = 1;
});
