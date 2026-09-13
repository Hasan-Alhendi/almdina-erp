"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

function source(relative) {
    return fs.readFileSync(path.resolve(__dirname, relative), "utf8");
}

const sequence = [];
const frm = {
    doctype: "Door Cutting Order",
    doc: { name: "DCO-OFFCUT-LIFECYCLE" },
};

const windowObject = {
    cur_frm: frm,
    dispatchEvent() {},
};

const fakeFrappe = {
    async call(request) {
        sequence.push("mutation");
        assert.match(request.method, /offcut_service\.set_offcut_execution_owner$/);
        return {
            message: {
                cutting_plan: "CP-UPLOADED",
                dependencies: {
                    changed: ["plan", "cost"],
                    reason: "offcut_classification_changed",
                },
            },
        };
    },
};

const context = vm.createContext({
    window: windowObject,
    frappe: fakeFrappe,
    console,
    Promise,
    Object,
    Array,
    String,
    Boolean,
    JSON,
    Map,
    Set,
    CustomEvent: class CustomEvent {
        constructor(type, init = {}) {
            this.type = type;
            this.detail = init.detail;
        }
    },
    __: value => value,
});

vm.runInContext(
    source("../../public/js/door_cutting_order/core/door_cutting_order_workspace_sync_coordinator.js"),
    context
);

const coordinator = windowObject.AlmdinaWorkspaceSyncCoordinator;
coordinator.register("plan", {
    invalidate(_frm, reason) {
        sequence.push(`invalidate:plan:${reason}`);
        return true;
    },
    async load() {
        sequence.push("load:plan:start");
        await Promise.resolve();
        sequence.push("load:plan:end");
    },
    canLoad() { return true; },
});
coordinator.register("cost", {
    invalidate(_frm, reason) {
        sequence.push(`invalidate:cost:${reason}`);
        return true;
    },
    async load() {
        sequence.push("load:cost:start");
        await Promise.resolve();
        sequence.push("load:cost:end");
    },
    canLoad() { return true; },
});

vm.runInContext(
    source("../../public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_workspace_api.js"),
    context
);

(async () => {
    const result = await windowObject.AlmdinaPlanWorkspaceAPI.saveOffcutAssignments(
        "CP-UPLOADED",
        [{ piece_instance_id: "piece:1", business_state: "CUSTOMER_CUSTOMER" }]
    );

    assert.equal(result.cutting_plan, "CP-UPLOADED");
    assert.deepEqual(sequence, [
        "mutation",
        "invalidate:plan:offcut_classification_changed",
        "invalidate:cost:offcut_classification_changed",
        "load:plan:start",
        "load:plan:end",
        "load:cost:start",
        "load:cost:end",
    ]);
    assert.ok(
        sequence.indexOf("load:cost:start") > sequence.indexOf("load:plan:end"),
        "Cost refresh must not start before the canonical Plan refresh has completed"
    );

    console.log("OFFCUT mutation Plan-to-Cost reconciliation simulation passed");
})().catch((error) => {
    console.error(error);
    process.exitCode = 1;
});
