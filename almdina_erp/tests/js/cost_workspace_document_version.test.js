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

const handlers = new Map();
let apiCalls = 0;
let serverModified = "server-1";
let offcutPriceApplicable = false;
let factoryExecutionQty = 2;

const frm = {
    doctype: "Door Cutting Order",
    doc: { name: "DCO-1", modified: "client-opened" },
    is_new() { return false; },
    is_dirty() { return false; },
};

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
        async load(orderName) {
            apiCalls += 1;
            return {
                order_name: orderName,
                order_modified: serverModified,
                order: {
                    total_cost_usd: 100,
                    offcut_price_applicable: offcutPriceApplicable,
                },
                pieces: [{ name: "ROW-1", factory_execution_qty: factoryExecutionQty }],
            };
        },
    },
};

const fakeFrappe = {
    ui: {
        form: {
            on(doctype, mapping) { handlers.set(doctype, mapping); },
        },
    },
};

const context = vm.createContext({
    window: windowObject,
    frappe: fakeFrappe,
    console,
    structuredClone,
    JSON,
    Set,
    Map,
    Date,
    Object,
    String,
    Boolean,
    Array,
    CustomEvent: FakeCustomEvent,
});

vm.runInContext(
    source("../../public/js/door_cutting_order/core/door_cutting_order_workspace_store.js"),
    context
);
vm.runInContext(
    source("../../public/js/door_cutting_order/core/door_cutting_order_workspace_sync_coordinator.js"),
    context
);
vm.runInContext(
    source("../../public/js/door_cutting_order/costing/door_cutting_order_cost_workspace_state.js"),
    context
);

const owner = windowObject.AlmdinaCostWorkspaceState;
assert.ok(owner);

(async () => {
    await owner.load(frm, { force: true });
    assert.equal(apiCalls, 1);
    assert.equal(frm.doc.modified, "client-opened",
        "a Cost GET must never advance the DCO optimistic-concurrency token");
    assert.equal(owner.snapshot(frm).freshness, "fresh");

    offcutPriceApplicable = true;
    factoryExecutionQty = 1;
    serverModified = "server-offcut-factory";
    owner.invalidate(frm, "offcut_classification_changed");
    await owner.load(frm, { force: true });
    assert.equal(apiCalls, 2);
    assert.equal(owner.snapshot(frm).freshness, "fresh");
    assert.equal(owner.settings(frm).offcut_price_applicable, true);
    assert.equal(owner.snapshot(frm).data.pieces[0].factory_execution_qty, 1);
    assert.equal(frm.doc.modified, "client-opened");

    owner.invalidate(frm, "order_inputs_changed");
    assert.equal(owner.snapshot(frm).freshness, "stale");
    serverModified = "server-2";
    await owner.load(frm);
    assert.equal(apiCalls, 3,
        "ordinary load must bypass its ready cache when the workspace is stale");
    assert.equal(frm.doc.modified, "client-opened");
    assert.equal(owner.snapshot(frm).freshness, "fresh");

    frm.is_dirty = () => true;
    serverModified = "server-3";
    await owner.load(frm, { force: true });
    assert.equal(frm.doc.modified, "client-opened");
    assert.equal(frm.__almdina_pending_server_modified, undefined,
        "read-only snapshots must not install a pending server write token either");

    console.log("Cost workspace read-version simulation passed");
})().catch((error) => {
    console.error(error);
    process.exitCode = 1;
});
