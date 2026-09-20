"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

function source(relative) {
    return fs.readFileSync(path.resolve(__dirname, relative), "utf8");
}

class FakeCustomEvent {
    constructor(type, init = {}) {
        this.type = type;
        this.detail = init.detail;
    }
}

function payload(orderName, total = 100) {
    return {
        order_name: orderName,
        order: {
            total_cost_usd: total,
            board_rate_usd: 10,
            cutting_cost_per_board_usd: 2,
        },
        pieces: [],
    };
}

const frm = {
    doctype: "Door Cutting Order",
    doc: { name: "DCO-1", modified: "client-opened" },
    is_new() { return false; },
    is_dirty() { return false; },
};

let loadCalls = 0;
let resolveFirstLoad;
const firstLoadGate = new Promise((resolve) => {
    resolveFirstLoad = resolve;
});

const windowObject = {
    cur_frm: frm,
    dispatchEvent() {},
    addEventListener() {},
    requestAnimationFrame(callback) { callback(); },
    AlmdinaDocumentContext: {
        formIdentity(form) { return `Door Cutting Order::${form.doc.name}`; },
        scheduleFrame(_form, _key, callback) { callback(); },
    },
    AlmdinaPermissions: {
        canDocument() { return true; },
    },
    AlmdinaCostWorkspaceAPI: {
        load(orderName) {
            loadCalls += 1;
            if (loadCalls === 1) {
                return firstLoadGate.then(() => payload(orderName, 11));
            }
            return Promise.resolve(payload(orderName, 22));
        },
    },
};

const context = vm.createContext({
    window: windowObject,
    frappe: { ui: { form: { on() {} } } },
    console,
    structuredClone,
    JSON,
    Set,
    Map,
    Date,
    Object,
    String,
    Boolean,
    Number,
    Error,
    Array,
    Promise,
    CustomEvent: FakeCustomEvent,
});

vm.runInContext(
    source("../../public/js/door_cutting_order/core/door_cutting_order_workspace_store.js"),
    context
);
vm.runInContext(
    source("../../public/js/door_cutting_order/costing/door_cutting_order_cost_workspace_state.js"),
    context
);

const owner = windowObject.AlmdinaCostWorkspaceState;
assert.ok(owner);

(async () => {
    const pending = owner.load(frm);
    assert.equal(owner.snapshot(frm).status, "loading");
    assert.equal(loadCalls, 1);

    owner.invalidate(frm, "order_inputs_changed");
    assert.equal(owner.snapshot(frm).status, "loading",
        "invalidation must keep an in-flight Cost workspace in loading until a later GET");

    resolveFirstLoad();
    const settled = await pending;

    assert.equal(loadCalls, 2,
        "a GET started before invalidation must be followed by a recovery GET");
    assert.equal(settled.status, "ready");
    assert.equal(owner.snapshot(frm).status, "ready");
    assert.equal(owner.snapshot(frm).freshness, "fresh");
    assert.equal(owner.snapshot(frm).data.order.total_cost_usd, 22);

    console.log("Cost workspace abandoned-load recovery passed");
})().catch((error) => {
    console.error(error);
    process.exitCode = 1;
});
