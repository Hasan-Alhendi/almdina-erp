"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(
    path.resolve(__dirname, "../../public/js/door_cutting_order/core/door_cutting_order_document_context.js"),
    "utf8"
);

const handlers = {};
const scheduledTimers = new Map();
let nextTimer = 0;
const dispatchedEvents = [];

const fakeWindow = {
    cur_frm: null,
    setTimeout(callback, delay = 0) {
        nextTimer += 1;
        scheduledTimers.set(nextTimer, { callback, delay });
        return nextTimer;
    },
    clearTimeout(timer) {
        scheduledTimers.delete(timer);
    },
    dispatchEvent(event) {
        dispatchedEvents.push(event.type);
    },
    addEventListener() {},
};

const fakeFrappe = {
    ui: {
        form: {
            on(doctype, events) {
                assert.equal(doctype, "Door Cutting Order");
                Object.assign(handlers, events);
            },
        },
    },
};

const context = vm.createContext({
    window: fakeWindow,
    frappe: fakeFrappe,
    console,
    Promise,
    Map,
    Set,
    Object,
    String,
    Number,
    CustomEvent: class CustomEvent {
        constructor(type, options = {}) {
            this.type = type;
            this.detail = options.detail;
        }
    },
});
vm.runInContext(source, context, { filename: "door_cutting_order_document_context.js" });

const frm = {
    doctype: "Door Cutting Order",
    doc: { doctype: "Door Cutting Order", name: "DCO-2026-00001" },
    fields_dict: {},
    is_new() { return false; },
};
fakeWindow.cur_frm = frm;
handlers.before_load(frm);

let recoveries = 0;
const owner = fakeWindow.AlmdinaDocumentContext;
owner.registerSurface("restricted-role-stubborn-surface", {
    isReady() { return false; },
    recover() {
        recoveries += 1;
        // Models the production/lifecycle callbacks that used to ask the owner
        // to settle immediately when their async recovery completed. Without an
        // in-flight guard this recursively starts another recovery pass forever.
        owner.settleSurfaces(frm, 0);
        return Promise.resolve(false);
    },
});

async function flushPromises() {
    await Promise.resolve();
    await Promise.resolve();
    await new Promise(resolve => setImmediate(resolve));
}

async function runNextTimer() {
    const first = [...scheduledTimers.entries()].sort((a, b) => a[0] - b[0])[0];
    if (!first) return false;
    const [id, timer] = first;
    scheduledTimers.delete(id);
    timer.callback();
    await flushPromises();
    return true;
}

(async () => {
    assert.equal(owner.settleSurfaces(frm, 0), false);
    assert.equal(recoveries, 1, "re-entrant recovery must be suppressed immediately");
    await flushPromises();

    // The central owner may retry only through its bounded backoff sequence.
    // A permanently unready restricted-role surface therefore cannot generate an
    // unbounded network loop or eventually exhaust the browser memory.
    while (await runNextTimer()) {
        assert.ok(recoveries <= 4, "surface recovery exceeded the bounded retry budget");
    }

    assert.equal(recoveries, 4);
    assert.equal(scheduledTimers.size, 0);
    assert.equal(frm.__almdinaSurfaceSettleRun, null);
    assert.equal(dispatchedEvents.includes("almdina:surfaces-settled"), false);

    console.log("Door Cutting Order surface settle re-entry guard passed");
})().catch(error => {
    console.error(error);
    process.exitCode = 1;
});
