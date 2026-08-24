"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

const source = fs.readFileSync(
    "almdina_erp/public/js/shop_floor_inbox/dialogs.js",
    "utf8"
);

const confirms = [];
const prompts = [];
const messages = [];
const alerts = [];
let active = true;

function child() {
    return { hidden: 0, hide() { this.hidden += 1; } };
}

const context = {
    console,
    Array,
    Map,
    Object,
    String,
    Promise,
    __(value) { return value; },
    frappe: {
        confirm(message, yes, no) {
            const surface = child();
            confirms.push({ message, yes, no, surface });
            return surface;
        },
        prompt(fields, submit) {
            const surface = child();
            prompts.push({ fields, submit, surface });
            return surface;
        },
        msgprint(payload) {
            const surface = child();
            messages.push({ payload, surface });
            return surface;
        },
        show_alert(payload) { alerts.push(payload); },
    },
    window: {},
};
vm.createContext(context);
vm.runInContext(source, context, { filename: "shop_floor_inbox/dialogs.js" });

const owner = context.window.AlmdinaShopFloorInboxDialogs.create({
    isCurrentGeneration: generation => active && generation === 7,
});
let terminalRuns = 0;
let logoutRuns = 0;
let workerRuns = 0;

owner.confirmTerminal(7, () => { terminalRuns += 1; });
owner.confirmTerminal(7, () => { terminalRuns += 1; });
assert.equal(confirms[0].surface.hidden, 1, "same-key confirmation ownership must replace the previous child");
owner.confirmLogout(7, () => { logoutRuns += 1; });
owner.promptWorker({
    workers: [{ name: "worker@example.com", full_name: "Worker" }],
    next_department: "CNC",
}, 7, () => { workerRuns += 1; });
owner.noWorkers({ operational_role: "CNC" }, 7);
owner.error("failed", 7);
owner.success("saved", 7);
assert.equal(alerts.length, 1);

active = false;
owner.deactivate();
for (const confirmation of confirms.slice(1)) assert.equal(confirmation.surface.hidden, 1);
assert.equal(prompts[0].surface.hidden, 1, "an unsubmitted worker selection is discarded on deactivate");
for (const message of messages) assert.equal(message.surface.hidden, 1);

confirms[1].yes();
confirms[2].yes();
prompts[0].submit({ next_assignee: "worker@example.com" });
owner.success("stale", 7);
owner.error("stale", 7);
assert.equal(terminalRuns, 0);
assert.equal(logoutRuns, 0);
assert.equal(workerRuns, 0);
assert.equal(alerts.length, 1, "stale child callbacks must not emit feedback");
assert.equal(messages.length, 2, "stale errors must not open a new child surface");
assert.equal(owner.dispose(), true);
assert.equal(owner.dispose(), false);

console.log("Shop Floor transient-child ownership simulation passed");
