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

const calls = [];
const alerts = [];
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

const context = {
    console,
    __(value) { return value; },
    frappe: {
        call(options) {
            calls.push(options);
            if (options.method.endsWith("get_handoff_context")) {
                return Promise.resolve({ message: handoffContext });
            }
            return Promise.resolve({ message: { ok: true } });
        },
        confirm(message, yes) { yes(); },
        prompt(fields, submit) { submit({ next_assignee: "cnc@example.com" }); },
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

    await api.perform({ stage: "PST-1", canStart: true }, { button });
    assert(calls[0].method.endsWith("start_my_stage"));
    assert.strictEqual(calls[0].args.stage_name, "PST-1");

    await api.perform({
        stage: "PST-2",
        stageType: "Drawing",
        canHandoff: true,
    }, { button });
    await new Promise(resolve => setImmediate(resolve));
    assert(calls.some(call => call.method.endsWith("get_handoff_context")));
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
        stage: "PST-FINAL",
        stageType: "Packing",
        canHandoff: true,
    }, { button });
    await new Promise(resolve => setImmediate(resolve));
    assert(calls.some(call => (
        call.method.endsWith("handoff_to_next")
        && call.args.stage_name === "PST-FINAL"
        && !Object.prototype.hasOwnProperty.call(call.args, "next_assignee")
    )));

    assert(alerts.length >= 3);
    assert.strictEqual(button.disabled, false);

    console.log("Shop-floor route-aware quick-action simulation passed");
})().catch(error => {
    console.error(error);
    process.exitCode = 1;
});
