"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(
    path.resolve(__dirname, "../../public/js/door_cutting_order/core/door_cutting_order_edit_session_coordinator.js"),
    "utf8"
);

function makeForm(name) {
    return {
        doctype: "Door Cutting Order",
        doc: { doctype: "Door Cutting Order", name },
        _almdinaDocumentContextGeneration: 0,
        events: 0,
        trigger(name) {
            if (name === "almdina_edit_session_changed") this.events += 1;
        },
    };
}

function createRuntime() {
    const window = {};
    const context = vm.createContext({ window, Object, String, Number, Boolean, Promise, Set, WeakMap });
    vm.runInContext(source, context, { filename: "door_cutting_order_edit_session_coordinator.js" });
    return { window, coordinator: window.AlmdinaDcoEditSessionCoordinator };
}

async function run() {
    const { window, coordinator } = createRuntime();
    const form = makeForm("DCO-A");
    window.cur_frm = form;
    const calls = [];
    ["order", "plan", "cost"].forEach(kind => {
        coordinator.register(kind, {
            canStart() { return true; },
            start() { calls.push(`start:${kind}`); return true; },
            save() { calls.push(`save:${kind}`); return true; },
            cancel() { calls.push(`cancel:${kind}`); return true; },
        });
    });

    assert.equal(await coordinator.start(form, "order"), true);
    assert.equal(coordinator.snapshot(form).activeKind, "order");
    assert.equal(await coordinator.start(form, "plan"), false);
    assert.equal(await coordinator.start(form, "cost"), false);
    assert.equal(await coordinator.cancel(form, "order"), true);
    const cancelled = coordinator.snapshot(form);
    assert.equal(cancelled.activeKind, null);
    assert.equal(cancelled.phase, "idle");
    assert.equal(cancelled.documentIdentity, "Door Cutting Order::DCO-A");
    assert.equal(cancelled.documentGeneration, 0);
    assert.equal(cancelled.sessionGeneration, 1);
    assert.equal(cancelled.editing, false);

    coordinator.register("plan", { canStart() { return true; }, start() { return false; } });
    assert.equal(await coordinator.start(form, "plan"), false);
    assert.equal(coordinator.snapshot(form).phase, "idle", "failed start must roll back atomically");

    coordinator.register("cost", {
        canStart() { return true; },
        start() { return true; },
        save() { return false; },
        cancel() { return true; },
    });
    assert.equal(await coordinator.start(form, "cost"), true);
    assert.equal(await coordinator.save(form, "cost"), false);
    assert.equal(coordinator.snapshot(form).phase, "editing", "failed save must preserve the open draft session");
    assert.equal(await coordinator.cancel(form, "cost"), true);

    assert.equal(coordinator.adoptLegacyEditing(form, "order"), true);
    assert.equal(coordinator.snapshot(form).activeKind, "order");
    assert.equal(coordinator.adoptLegacyEditing(form, "plan"), false, "legacy recovery cannot create a second session");
    assert.equal(await coordinator.cancel(form, "order"), true);

    let completeStart;
    coordinator.register("plan", {
        canStart() { return true; },
        start() { return new Promise(resolve => { completeStart = resolve; }); },
    });
    const pending = coordinator.start(form, "plan");
    const formB = makeForm("DCO-B");
    window.cur_frm = formB;
    completeStart(true);
    assert.equal(await pending, false, "completion from DCO-A must never commit into DCO-B");
    assert.equal(coordinator.snapshot(formB).phase, "idle");
    assert.equal(calls.includes("start:order"), true);
}

run().then(() => console.log("dco edit-session coordinator tests passed"));
