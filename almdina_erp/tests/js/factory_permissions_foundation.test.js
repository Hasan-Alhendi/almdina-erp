"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

function source(relativePath) {
    return fs.readFileSync(path.resolve(__dirname, "../../public/js/factory_permissions", relativePath), "utf8");
}

function createGate() {
    let generation = 0;
    return {
        begin(meta = null) {
            generation += 1;
            return Object.freeze({ generation, meta });
        },
        isCurrent(token) {
            return Boolean(token && token.generation === generation);
        },
        invalidate() {
            generation += 1;
            return generation;
        },
        generation() {
            return generation;
        },
    };
}

function createLifecycle() {
    return {
        track() {},
        timeout() {},
        dispose() {},
    };
}

const rpcCalls = [];
const fakeWindow = {
    AlmdinaFrontend: {
        rpc(method, args, options) {
            rpcCalls.push({ method, args, options });
            return Promise.resolve({ ok: true });
        },
        createLatestRequestGate: createGate,
        createLifecycleScope: createLifecycle,
    },
};
const context = vm.createContext({
    window: fakeWindow,
    console,
    Object,
    Array,
    Set,
    String,
    Number,
    Boolean,
    JSON,
    Promise,
});

vm.runInContext(source("api.js"), context, { filename: "api.js" });
vm.runInContext(source("state.js"), context, { filename: "state.js" });

(async () => {
    const api = fakeWindow.AlmdinaFactoryPermissionsApi;
    const stateModule = fakeWindow.AlmdinaFactoryPermissionsState;

    await api.getConsole({ freeze: false });
    await api.getRole("CNC", { freeze: false });
    await api.previewRole("CNC", { view_orders: true });
    await api.exportRole("CNC", { freeze: true, freezeMessage: "export" });
    await api.previewImport("CNC", '{"role":"CNC"}', { freeze: true });
    await api.updateRole("CNC", { view_orders: true }, true, { freeze: true, freezeMessage: "save" });

    assert.equal(rpcCalls.length, 6);
    assert.equal(
        rpcCalls[0].method,
        "almdina_erp.almdina_erp.services.permission_management_service.get_permission_console"
    );
    assert.equal(JSON.stringify(rpcCalls[1].args), JSON.stringify({ role: "CNC" }));
    assert.equal(JSON.parse(rpcCalls[2].args.capabilities).view_orders, true);
    assert.equal(rpcCalls[3].options.freezeMessage, "export");
    assert.equal(rpcCalls[4].args.payload, '{"role":"CNC"}');
    assert.equal(rpcCalls[5].args.confirm_self_lockout, 1);
    assert.equal(JSON.parse(rpcCalls[5].args.capabilities).view_orders, true);

    const first = stateModule.create();
    const second = stateModule.create();
    assert.notEqual(first.data, second.data, "Each page mount owns an isolated mutable state object");

    first.data.baseline = { edit_order: false, view_orders: true };
    first.data.working = { view_orders: true, edit_order: false };
    assert.equal(first.isDirty(), false, "Key ordering must not create a false dirty state");
    first.data.working.edit_order = true;
    assert.equal(first.isDirty(), true);

    const oldRole = first.requests.role.begin({ role: "A" });
    const newRole = first.requests.role.begin({ role: "B" });
    assert.equal(first.requests.role.isCurrent(oldRole), false);
    assert.equal(first.requests.role.isCurrent(newRole), true);

    const preview = first.requests.preview.begin();
    const transfer = first.requests.transfer.begin();
    first.invalidatePending();
    assert.equal(first.requests.preview.isCurrent(preview), false);
    assert.equal(first.requests.transfer.isCurrent(transfer), false);

    assert.equal(
        JSON.stringify(first.unique(["view", "view", "", null, "edit"])),
        JSON.stringify(["view", "edit"])
    );
    console.log("Factory permissions API/state foundation simulation passed");
})().catch(error => {
    console.error(error);
    process.exitCode = 1;
});
