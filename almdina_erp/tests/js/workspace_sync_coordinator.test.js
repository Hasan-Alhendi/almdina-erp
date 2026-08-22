"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(
    path.resolve(
        __dirname,
        "../../public/js/door_cutting_order/core/door_cutting_order_workspace_sync_coordinator.js"
    ),
    "utf8"
);

class FakeCustomEvent {
    constructor(type, init = {}) {
        this.type = type;
        this.detail = init.detail;
    }
}

const events = [];
const windowObject = {
    dispatchEvent(event) {
        events.push(event);
    },
    AlmdinaDocumentContext: {
        formIdentity(frm) {
            return `Door Cutting Order::${frm.doc.name}`;
        },
    },
};

const context = vm.createContext({
    window: windowObject,
    console,
    Map,
    Set,
    Object,
    String,
    Boolean,
    Array,
    CustomEvent: FakeCustomEvent,
});

vm.runInContext(source, context, {
    filename: "door_cutting_order_workspace_sync_coordinator.js",
});

const coordinator = windowObject.AlmdinaWorkspaceSyncCoordinator;
assert.ok(coordinator);

const order = [];
const invalidations = [];
const snapshots = {
    plan: { freshness: "fresh" },
    cost: { freshness: "fresh" },
};

function descriptor(name) {
    return {
        canLoad() {
            return true;
        },
        invalidate(_frm, reason) {
            invalidations.push([name, reason]);
            snapshots[name] = { freshness: "stale", staleReason: reason };
            return snapshots[name];
        },
        async load(_frm, options) {
            order.push(`${name}:start:${options.force ? "force" : "cached"}`);
            await Promise.resolve();
            snapshots[name] = { freshness: "fresh" };
            order.push(`${name}:end`);
            return snapshots[name];
        },
        snapshot() {
            return snapshots[name];
        },
    };
}

assert.equal(coordinator.register("plan", descriptor("plan")), true);
assert.equal(coordinator.register("cost", descriptor("cost")), true);

const frm = {
    doctype: "Door Cutting Order",
    doc: { name: "DCO-1", modified: "old" },
    is_dirty() {
        return false;
    },
};

(async () => {
    const affected = coordinator.invalidate(frm, ["plan", "cost"], "order_inputs_changed");
    assert.deepEqual(Array.from(affected), ["plan", "cost"]);
    assert.deepEqual(invalidations, [
        ["plan", "order_inputs_changed"],
        ["cost", "order_inputs_changed"],
    ]);
    assert.equal(coordinator.snapshot(frm, "cost").freshness, "stale");

    await coordinator.refresh(frm, ["plan", "cost"], {
        force: true,
        reason: "canonical_reload",
    });
    assert.deepEqual(order, [
        "plan:start:force",
        "plan:end",
        "cost:start:force",
        "cost:end",
    ], "Plan must settle before Cost loads because Cost can depend on canonical Plan lineage");
    assert.equal(coordinator.snapshot(frm, "plan").freshness, "fresh");
    assert.equal(coordinator.snapshot(frm, "cost").freshness, "fresh");

    assert.equal(coordinator.syncDocumentModified(frm, "server-1"), true);
    assert.equal(frm.doc.modified, "server-1");
    assert.equal(frm.__almdina_pending_server_modified, null);

    frm.is_dirty = () => true;
    assert.equal(coordinator.syncDocumentModified(frm, "server-2"), false);
    assert.equal(frm.doc.modified, "server-1", "dirty forms must keep their optimistic concurrency token");
    assert.equal(frm.__almdina_pending_server_modified, "server-2");

    frm.is_dirty = () => false;
    order.length = 0;
    invalidations.length = 0;
    const result = await coordinator.reconcile(frm, {
        changed: ["plan", "cost"],
        invalidated: [],
        reason: "plan_changed",
        order_modified: "server-3",
    });
    assert.deepEqual(Array.from(result.changed), ["plan", "cost"]);
    assert.equal(result.documentModifiedSynced, true);
    assert.equal(frm.doc.modified, "server-3");
    assert.deepEqual(invalidations, [
        ["plan", "plan_changed"],
        ["cost", "plan_changed"],
    ]);
    assert.deepEqual(order, [
        "plan:start:force",
        "plan:end",
        "cost:start:force",
        "cost:end",
    ]);

    assert.ok(
        events.some(event => event.type === "almdina:workspace-freshness-changed"),
        "coordinator must publish one reusable freshness event contract"
    );

    console.log("Workspace sync coordinator simulation passed");
})().catch((error) => {
    console.error(error);
    process.exitCode = 1;
});
