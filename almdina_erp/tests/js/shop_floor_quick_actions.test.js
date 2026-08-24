"use strict";

const assert = require("assert");
const fs = require("fs");
const vm = require("vm");

const source = fs.readFileSync(
    "almdina_erp/public/js/shop_floor_quick_actions.js",
    "utf8"
);

assert(!source.includes('context.stageType === "Sanding"'), "quick actions must not hard-code the final production stage");
assert(source.includes("get_handoff_context"), "handoff decisions must come from the server routing context");
assert(source.includes("mark_delivered"), "delivery must reuse the existing server delivery command");
assert(!source.includes("frappe.get_roles"), "quick actions must not add client-side role-name authorization");
assert(!source.includes('fieldtype: "Select"'), "worker handoff must not use a native mobile select picker");
assert(!source.includes("frappe.prompt("), "worker handoff must use the anchored dropdown dialog instead of prompt Select");
assert(source.includes("shop_floor_worker_dropdown.css"), "the focused worker dropdown stylesheet must be lazy-loaded");
assert(source.includes("function lifecycleBoundary(options = {})"), "quick actions must accept caller-owned lifecycle capability");
assert(source.includes("owner.isCurrent"), "quick-action UI commits must ask the caller whether the visit is current");
assert(source.includes("owner.ownTransient"), "quick-action child surfaces must remain caller-owned");
assert(source.includes("owner.onStaleMutationSuccess"), "stale mutation success must request caller reconciliation");
assert(!source.includes("AlmdinaMutationLifecycle"), "quick actions must not create a shared mutation framework");

const calls = [];
const alerts = [];
const dialogs = [];
let dropdownHideCount = 0;
let confirmationCount = 0;
let handoffContext = {
    final_stage: false,
    next_stage_type: "CNC",
    next_department: "CNC",
    operational_role: "عامل CNC",
    workers: [{ name: "cnc@example.com", full_name: "عامل CNC" }],
};
const button = {
    disabled: false,
    attributes: {},
    classList: { toggle() {} },
    setAttribute(name, value) { this.attributes[name] = value; },
};

class FakeDialog {
    constructor(config) {
        this.config = config;
        this.fields_dict = { next_assignee_dropdown: {} };
        dialogs.push(this);
    }

    show() {
        // The production surface renders an HTML dropdown. The simulation omits
        // a DOM and relies on the intentional single-worker preselection before
        // submitting the dialog action on the next microtask.
        Promise.resolve().then(() => this.config.primary_action());
    }

    hide() {
        dropdownHideCount += 1;
    }
}

const context = {
    console,
    Promise,
    __(value) { return value; },
    frappe: {
        ui: { Dialog: FakeDialog },
        call(options) {
            calls.push(options);
            if (options.method.endsWith("get_handoff_context")) {
                return Promise.resolve({ message: handoffContext });
            }
            if (options.method.endsWith("get_current_stage_context")) {
                return Promise.resolve({
                    message: {
                        actor_holds_operational_role: true,
                        can_start_stage: true,
                        can_handoff_stage: true,
                    },
                });
            }
            return Promise.resolve({ message: { ok: true } });
        },
        confirm(message, yes) {
            confirmationCount += 1;
            yes();
        },
        show_alert(message) { alerts.push(message); },
        msgprint(message) { throw new Error(message); },
    },
    window: {},
};
context.window.window = context.window;
vm.createContext(context);
vm.runInContext(source, context);

(async () => {
    const api = context.window.AlmdinaShopFloorQuickActions;
    assert.strictEqual(api.actionFor({ canStart: true }).label, "بدء العمل");
    assert.strictEqual(
        api.actionFor({ canHandoff: true, stageType: "Any Configured Stage" }).label,
        "إنهاء وإرسال"
    );

    const deliveryAction = api.actionFor({ canDeliver: true, canStart: true, canHandoff: true });
    assert.strictEqual(deliveryAction.kind, "deliver", "server-authorized delivery must take precedence over production actions");
    assert.strictEqual(deliveryAction.label, "تم التسليم");

    const callsBeforeDelivery = calls.length;
    await api.perform({ order: "DCO-DELIVER", canDeliver: true }, { button });
    const deliveryCalls = calls.slice(callsBeforeDelivery);
    assert.strictEqual(deliveryCalls.length, 1, "delivery must execute only the delivery command");
    assert(deliveryCalls[0].method.endsWith("mark_delivered"), "delivery must reuse mark_delivered");
    assert.strictEqual(deliveryCalls[0].args.order_name, "DCO-DELIVER");
    assert(
        !deliveryCalls.some(call => call.method.endsWith("get_current_stage_context")),
        "delivery is an independent authorized quick action and must not depend on a production-stage guard"
    );

    await api.perform({ order: "DCO-1", stage: "PST-1", canStart: true }, { button });
    const stageGuard = calls.find(call => call.method.endsWith("get_current_stage_context"));
    const startCall = calls.find(call => call.method.endsWith("start_my_stage"));
    assert(stageGuard, "quick actions must authorize the current production stage before mutation");
    assert.strictEqual(stageGuard.args.order_name, "DCO-1");
    assert(startCall, "authorized start action must call start_my_stage");
    assert.strictEqual(startCall.args.stage_name, "PST-1");

    await api.perform({
        order: "DCO-2",
        stage: "PST-2",
        stageType: "Drawing",
        canHandoff: true,
    }, { button });
    await new Promise(resolve => setImmediate(resolve));
    assert(calls.some(call => call.method.endsWith("get_handoff_context")));
    assert.strictEqual(dialogs.length, 1, "non-final handoff must open one worker dropdown dialog");
    assert.strictEqual(dialogs[0].config.title, "إنهاء وإرسال");
    assert.strictEqual(dialogs[0].config.fields[0].fieldtype, "HTML");
    assert.strictEqual(dropdownHideCount, 1, "handoff dialog must close after a worker is submitted");
    assert(calls.some(call => (
        call.method.endsWith("handoff_to_next")
        && call.args.next_assignee === "cnc@example.com"
    )));

    // The final stage is determined exclusively by the configured server route.
    handoffContext = {
        final_stage: true,
        next_stage_type: null,
        next_department: null,
        operational_role: null,
        workers: [],
    };
    await api.perform({
        order: "DCO-FINAL",
        stage: "PST-FINAL",
        stageType: "Packing",
        canHandoff: true,
    }, { button });
    await new Promise(resolve => setImmediate(resolve));
    assert.strictEqual(confirmationCount, 1, "the shared final-stage flow must keep its confirmation by default");
    assert(calls.some(call => (
        call.method.endsWith("handoff_to_next")
        && call.args.stage_name === "PST-FINAL"
        && !Object.prototype.hasOwnProperty.call(call.args, "next_assignee")
    )));

    // A caller that already confirmed the worker action (the mobile order card)
    // can suppress only the duplicate final-stage confirmation.
    const confirmationsBeforeMobileFinal = confirmationCount;
    await api.perform({
        order: "DCO-MOBILE-FINAL",
        stage: "PST-MOBILE-FINAL",
        stageType: "Packing",
        canHandoff: true,
    }, { button, skipFinalConfirmation: true });
    await new Promise(resolve => setImmediate(resolve));
    assert.strictEqual(
        confirmationCount,
        confirmationsBeforeMobileFinal,
        "an already-confirmed mobile handoff must not show a second confirmation"
    );
    assert(calls.some(call => (
        call.method.endsWith("handoff_to_next")
        && call.args.stage_name === "PST-MOBILE-FINAL"
    )));

    assert(alerts.length >= 5);
    assert.strictEqual(button.disabled, false);

    console.log("Shop-floor route-aware quick-action simulation passed");
})().catch(error => {
    console.error(error);
    process.exitCode = 1;
});
