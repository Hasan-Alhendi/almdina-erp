"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(
    path.resolve(__dirname, "../../public/js/frontend_foundation.js"),
    "utf8"
);

const calls = [];
const timers = new Map();
let nextTimer = 10;
const links = [];
const nodesById = new Map();

const fakeDocument = {
    head: {
        appendChild(node) {
            links.push(node);
            if (node.id) nodesById.set(node.id, node);
        },
    },
    createElement(tag) {
        assert.equal(tag, "link");
        return {};
    },
    getElementById(id) {
        return nodesById.get(id) || null;
    },
    querySelector(selector) {
        const match = selector.match(/href="([^"]+)"/);
        if (!match) return null;
        return links.find(link => link.rel === "stylesheet" && link.href === match[1]) || null;
    },
};

const fakeWindow = {
    document: fakeDocument,
    frappe: {
        call(request) {
            calls.push(request);
            if (request.method === "test.failure") return Promise.reject(new Error("server failed"));
            if (request.method === "test.raw") return Promise.resolve({ message: { ok: true }, extra: 9 });
            return Promise.resolve({ message: { ok: true, method: request.method } });
        },
    },
    setTimeout(callback) {
        nextTimer += 1;
        timers.set(nextTimer, callback);
        return nextTimer;
    },
    clearTimeout(timer) {
        timers.delete(timer);
    },
};

const context = vm.createContext({
    window: fakeWindow,
    console,
    Promise,
    Object,
    String,
    Number,
    Boolean,
    Array,
    Map,
    Error,
});
vm.runInContext(source, context, { filename: "frontend_foundation.js" });

const frontend = fakeWindow.AlmdinaFrontend;
assert.ok(frontend);
assert.equal(Object.isFrozen(frontend), true);

(async () => {
    const payload = await frontend.rpc("test.message", { value: 7 }, {
        freeze: true,
        freezeMessage: "Working",
    });
    assert.equal(payload.ok, true);
    assert.equal(payload.method, "test.message");
    assert.equal(calls[0].args.value, 7);
    assert.equal(calls[0].freeze, true);
    assert.equal(calls[0].freeze_message, "Working");

    const raw = await frontend.rpc("test.raw", {}, { raw: true });
    assert.equal(raw.extra, 9);
    await assert.rejects(frontend.rpc("test.failure"), /server failed/);
    await assert.rejects(frontend.rpc(""), /RPC method is required/);

    assert.equal(frontend.errorMessage(new Error("broken"), "fallback"), "broken");
    assert.equal(frontend.errorMessage({}, "fallback"), "fallback");

    const gate = frontend.createLatestRequestGate();
    const first = gate.begin({ mode: "first" });
    assert.equal(gate.isCurrent(first), true);
    const second = gate.begin({ mode: "second" });
    assert.equal(gate.isCurrent(first), false);
    assert.equal(gate.isCurrent(second), true);
    gate.invalidate();
    assert.equal(gate.isCurrent(second), false);

    const lifecycle = frontend.createLifecycleScope();
    const targetEvents = new Map();
    const target = {
        addEventListener(name, handler) { targetEvents.set(name, handler); },
        removeEventListener(name, handler) {
            if (targetEvents.get(name) === handler) targetEvents.delete(name);
        },
    };
    let eventRuns = 0;
    lifecycle.listen(target, "change", () => { eventRuns += 1; }, undefined, "page-change");
    targetEvents.get("change")();
    assert.equal(eventRuns, 1);

    let oldCleanupRuns = 0;
    let newCleanupRuns = 0;
    lifecycle.track(() => { oldCleanupRuns += 1; }, "owned-effect");
    lifecycle.track(() => { newCleanupRuns += 1; }, "owned-effect");
    assert.equal(oldCleanupRuns, 1, "re-registering one owner must clean the prior effect");

    let timerRuns = 0;
    const timer = lifecycle.timeout(() => { timerRuns += 1; }, 20, "refresh");
    assert.equal(timers.has(timer), true);

    let observerDisconnects = 0;
    lifecycle.observe({ disconnect() { observerDisconnects += 1; } }, "page-observer");
    assert.equal(lifecycle.isDisposed(), false);
    assert.equal(lifecycle.dispose(), true);
    assert.equal(lifecycle.dispose(), false, "dispose must be idempotent");
    assert.equal(targetEvents.size, 0);
    assert.equal(timers.has(timer), false);
    assert.equal(timerRuns, 0);
    assert.equal(observerDisconnects, 1);
    assert.equal(newCleanupRuns, 1);
    assert.equal(lifecycle.cleanupCount(), 0);

    const pendingStylesheet = frontend.ensureStylesheet(
        "/assets/almdina_erp/css/factory_permissions.css",
        { id: "factory-permissions-style" }
    );
    assert.equal(links.length, 1);
    assert.equal(links[0].rel, "stylesheet");
    assert.equal(links[0].href, "/assets/almdina_erp/css/factory_permissions.css");
    links[0].onload();
    const loadedLink = await pendingStylesheet;
    const reusedLink = await frontend.ensureStylesheet(
        "/assets/almdina_erp/css/factory_permissions.css",
        { id: "factory-permissions-style" }
    );
    assert.equal(reusedLink, loadedLink);
    assert.equal(links.length, 1, "stylesheet loading must be idempotent");

    console.log("Minimal frontend foundation simulation passed");
})().catch(error => {
    console.error(error);
    process.exitCode = 1;
});

// This file is already a permanent Static Checks gate. Keep the Page-entry race
// simulation attached to it so cold Desk bootstrap coverage cannot become orphaned.
require("./page_foundation_bootstrap.test.js");
