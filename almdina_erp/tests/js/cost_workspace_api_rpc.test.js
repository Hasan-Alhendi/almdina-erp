"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(
    path.resolve(
        __dirname,
        "../../public/js/door_cutting_order/costing/door_cutting_order_cost_workspace_api.js"
    ),
    "utf8"
);

function loadApi(frappe) {
    const context = vm.createContext({
        window: { frappe },
        frappe,
        __: value => value,
        Promise,
        Object,
    });
    vm.runInContext(source, context);
    return context.window.AlmdinaCostWorkspaceAPI;
}

(async () => {
    let xcallRequest;
    const xcallApi = loadApi({
        xcall(method, args) {
            xcallRequest = { method, args };
            return Promise.resolve({ order_name: args.order_name });
        },
    });
    const read = await xcallApi.load("DCO-XCALL");
    assert.equal(read.order_name, "DCO-XCALL");
    assert.equal(xcallRequest.args.order_name, "DCO-XCALL");

    let legacyRequest;
    const legacyApi = loadApi({
        call(request) {
            legacyRequest = request;
            request.callback({ message: { order_name: request.args.order_name } });
        },
    });
    const saved = await legacyApi.saveSettings("DCO-LEGACY", {
        board_rate_usd: 12,
        cutting_cost_per_board_usd: 3,
    });
    assert.equal(saved.order_name, "DCO-LEGACY");
    assert.equal(legacyRequest.freeze, true);
    assert.equal(typeof legacyRequest.callback, "function");
    assert.equal(typeof legacyRequest.error, "function");

    const errorApi = loadApi({
        call(request) {
            request.error(new Error("rpc-failed"));
        },
    });
    await assert.rejects(errorApi.saveSettings("DCO-ERROR", {}), /rpc-failed/);

    console.log("Cost workspace RPC compatibility simulation passed");
})().catch(error => {
    console.error(error);
    process.exitCode = 1;
});
