"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

const source = fs.readFileSync(
    "almdina_erp/public/js/shop_floor_inbox/interactions.js",
    "utf8"
);

const registrations = [];
const root = {
    off(namespace) {
        const resolved = String(namespace || "");
        for (let index = registrations.length - 1; index >= 0; index -= 1) {
            if (!resolved || registrations[index].event.endsWith(resolved)) registrations.splice(index, 1);
        }
        return this;
    },
    on(event, selector, handler) {
        registrations.push({ event: String(event), selector, handler });
        return this;
    },
    find() { return { removeClass() {} }; },
};

function lifecycleScope() {
    let cleanup = null;
    return {
        track(nextCleanup) {
            if (cleanup) cleanup();
            cleanup = nextCleanup;
        },
        dispose() {
            if (!cleanup) return;
            const current = cleanup;
            cleanup = null;
            current();
        },
    };
}

const context = {
    console,
    Object,
    String,
    window: {},
    $(value) { return value; },
};
vm.createContext(context);
vm.runInContext(source, context, { filename: "shop_floor_inbox/interactions.js" });

const interactions = context.window.AlmdinaShopFloorInboxInteractions;
const callbacks = {
    setMode() {},
    refresh() {},
    logout() {},
    openOrder() {},
    quickAction() {},
    setRouteFilter() {},
    setSearch() {},
    handoff() {},
};

const firstLifecycle = lifecycleScope();
const firstOwner = interactions.bind({ $section: root }, firstLifecycle, callbacks);
const ownedRegistrationCount = registrations.length;
assert.ok(ownedRegistrationCount >= 10, "delegated click/search/drag-drop handlers must share one owner");
firstOwner.deactivate();
assert.equal(registrations.length, ownedRegistrationCount, "hide suspends drag state without unbinding mounted handlers");
firstLifecycle.dispose();
assert.equal(registrations.length, 0, "real disposal must remove every delegated handler");

const secondLifecycle = lifecycleScope();
interactions.bind({ $section: root }, secondLifecycle, callbacks);
assert.equal(registrations.length, ownedRegistrationCount, "remount must not duplicate delegated or drag-drop handlers");
secondLifecycle.dispose();
assert.equal(registrations.length, 0);

console.log("Shop Floor interaction ownership simulation passed");
