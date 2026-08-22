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

const frm = {
    doctype: "Door Cutting Order",
    doc: { name: "DCO-1", modified: "client-old" },
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
                order: { total_cost_usd: 100 },
                pieces: [],
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
    assert.equal(frm.doc.modified, "server-1",
        "canonical Cost read must advance a clean form to the current DCO version");
    assert.equal(owner.snapshot(frm).freshness, "fresh");

    owner.invalidate(frm, "order_inputs_changed");
    assert.equal(owner.snapshot(frm).freshness, "stale");
    serverModified = "server-2";
    await owner.load(frm);
    assert.equal(apiCalls, 2,
        "ordinary load must bypass its ready cache when the workspace is stale");
    assert.equal(frm.doc.modified, "server-2");
    assert.equal(owner.snapshot(frm).freshness, "fresh");

    frm.is_dirty = () => true;
    serverModified = "server-3";
    await owner.load(frm, { force: true });
    assert.equal(frm.doc.modified, "server-2",
        "a real local edit must preserve the original optimistic-concurrency token");
    assert.equal(frm.__almdina_pending_server_modified, "server-3");

    console.log("Cost workspace document-version simulation passed");
})().catch((error) => {
    console.error(error);
    process.exitCode = 1;
});
