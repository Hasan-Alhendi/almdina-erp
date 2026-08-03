"use strict";

const assert = require("assert");
const fs = require("fs");
const vm = require("vm");

const source = fs.readFileSync(
    "almdina_erp/public/js/shop_floor_quick_actions.js",
    "utf8"
);

const calls = [];
const alerts = [];
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
            if (options.method.endsWith("get_handoff_workers")) {
                return Promise.resolve({
                    message: [{ name: "cnc@example.com", full_name: "عامل CNC" }],
                });
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
        api.actionFor({ canHandoff: true, stageType: "Sanding" }).label,
        "إنهاء التقشيط"
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
    assert(calls.some(call => call.method.endsWith("get_handoff_workers")));
    assert(calls.some(call => (
        call.method.endsWith("handoff_to_next")
        && call.args.next_assignee === "cnc@example.com"
    )));
    assert(alerts.length >= 2);
    assert.strictEqual(button.disabled, false);

    console.log("Shop-floor quick-action simulation passed");
})().catch(error => {
    console.error(error);
    process.exitCode = 1;
});
