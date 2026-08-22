const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const source = fs.readFileSync(
    path.join(
        __dirname,
        "../../public/js/door_cutting_order/core/door_cutting_order_workspace_store.js"
    ),
    "utf8"
);

const context = {
    console,
    structuredClone,
    JSON,
    Set,
    Date,
};
context.window = context;
vm.createContext(context);
vm.runInContext(source, context, { filename: "door_cutting_order_workspace_store.js" });

const factory = context.AlmdinaWorkspaceStore;
assert(factory && typeof factory.create === "function");

const store = factory.create("plan");
let emitted = 0;
const unsubscribe = store.subscribe(() => {
    emitted += 1;
});

assert.strictEqual(store.snapshot().freshness, "unknown");

const firstRequest = store.beginLoad("Door Cutting Order::DCO-1");
assert.strictEqual(store.snapshot().status, "loading");

const secondRequest = store.beginLoad("Door Cutting Order::DCO-2");
assert(secondRequest > firstRequest);
assert.strictEqual(store.snapshot().identity, "Door Cutting Order::DCO-2");

assert.strictEqual(
    store.resolveLoad("Door Cutting Order::DCO-1", firstRequest, { name: "stale" }),
    false,
    "a response captured for the previous order must never replace the active order"
);
assert.strictEqual(store.snapshot().data, null);

assert.strictEqual(
    store.resolveLoad("Door Cutting Order::DCO-2", secondRequest, {
        settings: { kerf_mm: 3 },
    }),
    true
);
assert.strictEqual(store.snapshot().status, "ready");
assert.strictEqual(store.snapshot().freshness, "fresh");
assert.strictEqual(store.isFresh(), true);
assert.strictEqual(store.snapshot().data.settings.kerf_mm, 3);

const escaped = store.snapshot();
escaped.data.settings.kerf_mm = 99;
assert.strictEqual(
    store.snapshot().data.settings.kerf_mm,
    3,
    "callers must receive a clone, not mutable store state"
);

const requestBeforeInvalidation = store.beginLoad("Door Cutting Order::DCO-2");
const invalidated = store.invalidate("order_inputs_changed");
assert.strictEqual(invalidated.status, "loading");
assert.strictEqual(invalidated.freshness, "stale");
assert.strictEqual(invalidated.staleReason, "order_inputs_changed");
assert.ok(invalidated.invalidatedAt);
assert.strictEqual(store.isFresh(), false);
assert.strictEqual(
    store.resolveLoad("Door Cutting Order::DCO-2", requestBeforeInvalidation, {
        settings: { kerf_mm: 77 },
    }),
    false,
    "a GET started before dependency invalidation must never repaint stale data"
);
assert.strictEqual(
    store.snapshot().data.settings.kerf_mm,
    3,
    "invalidation preserves the last known snapshot only as contextual data"
);

const refreshRequest = store.beginLoad("Door Cutting Order::DCO-2");
assert.strictEqual(
    store.resolveLoad("Door Cutting Order::DCO-2", refreshRequest, {
        settings: { kerf_mm: 4 },
    }),
    true
);
assert.strictEqual(store.snapshot().freshness, "fresh");
assert.strictEqual(store.snapshot().staleReason, null);
assert.strictEqual(store.snapshot().invalidatedAt, null);
assert.strictEqual(store.snapshot().data.settings.kerf_mm, 4);

const staleSameDocumentRequest = store.beginLoad("Door Cutting Order::DCO-2");
const committed = store.commit({ settings: { kerf_mm: 5 } });
assert.strictEqual(committed.status, "ready");
assert.strictEqual(committed.freshness, "fresh");
assert.strictEqual(committed.data.settings.kerf_mm, 5);
assert(
    committed.requestId > staleSameDocumentRequest,
    "an authoritative command commit must advance the request generation"
);
assert.strictEqual(
    store.resolveLoad("Door Cutting Order::DCO-2", staleSameDocumentRequest, {
        settings: { kerf_mm: 3 },
    }),
    false,
    "a GET started before an authoritative commit must never overwrite that commit"
);
assert.strictEqual(
    store.snapshot().data.settings.kerf_mm,
    5,
    "the authoritative committed value must survive a late stale GET"
);

assert.strictEqual(store.beginEdit(), true);
assert.strictEqual(store.snapshot().editing, true);
assert.strictEqual(store.patchDraft({ marker: "changed" }), true);
assert.strictEqual(store.snapshot().dirty, true);
assert.strictEqual(store.snapshot().data.settings.kerf_mm, 5);
assert.strictEqual(store.cancelEdit(), true);
assert.strictEqual(store.snapshot().editing, false);
assert.strictEqual(store.snapshot().dirty, false);
assert.strictEqual(store.snapshot().draft, null);

unsubscribe();
assert(emitted >= 11);

console.log("workspace_store.test.js passed");
