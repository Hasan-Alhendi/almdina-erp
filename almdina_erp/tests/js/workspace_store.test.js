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
assert.strictEqual(store.snapshot().data.settings.kerf_mm, 3);

const escaped = store.snapshot();
escaped.data.settings.kerf_mm = 99;
assert.strictEqual(
    store.snapshot().data.settings.kerf_mm,
    3,
    "callers must receive a clone, not mutable store state"
);

assert.strictEqual(store.beginEdit(), true);
assert.strictEqual(store.snapshot().editing, true);
assert.strictEqual(store.patchDraft({ marker: "changed" }), true);
assert.strictEqual(store.snapshot().dirty, true);
assert.strictEqual(store.snapshot().data.settings.kerf_mm, 3);
assert.strictEqual(store.cancelEdit(), true);
assert.strictEqual(store.snapshot().editing, false);
assert.strictEqual(store.snapshot().dirty, false);
assert.strictEqual(store.snapshot().draft, null);

unsubscribe();
assert(emitted >= 5);

console.log("workspace_store.test.js passed");
