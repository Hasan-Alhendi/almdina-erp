"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(
    path.resolve(__dirname, "../../public/js/page_revisit_refresh.js"),
    "utf8"
);

function createJqueryHarness() {
    const events = new WeakMap();

    function handlers(target) {
        if (!events.has(target)) events.set(target, new Map());
        return events.get(target);
    }

    function jquery(target) {
        return {
            on(eventName, callback) {
                handlers(target).set(String(eventName), callback);
                return this;
            },
            off(eventName) {
                const name = String(eventName || "");
                const owned = handlers(target);
                if (!name) owned.clear();
                else if (name.startsWith(".")) {
                    for (const key of owned.keys()) {
                        if (key.endsWith(name)) owned.delete(key);
                    }
                } else {
                    owned.delete(name);
                }
                return this;
            },
        };
    }

    function trigger(target, eventName) {
        const base = String(eventName);
        for (const [registered, callback] of [...handlers(target).entries()]) {
            if (registered.split(".")[0] === base) callback.call(target);
        }
    }

    return {
        jquery,
        trigger,
        listenerCount: target => handlers(target).size,
    };
}

function loadRuntime({ cachedOldApi = false } = {}) {
    const harness = createJqueryHarness();
    const frappe = { container: { page: null } };
    const windowObject = {
        frappe,
        jQuery: harness.jquery,
    };
    if (cachedOldApi) {
        windowObject.AlmdinaPageRevisit = Object.freeze({ refreshOnRevisit() {} });
    }
    const context = vm.createContext({
        window: windowObject,
        frappe,
        $: harness.jquery,
        console,
        Promise,
        Object,
        String,
        Boolean,
        Error,
    });
    vm.runInContext(source, context, { filename: "page_revisit_refresh.js" });
    return { api: windowObject.AlmdinaPageRevisit, frappe, harness };
}

(() => {
    const { api, frappe, harness } = loadRuntime();
    const wrapper = {};
    const otherPage = {};
    const events = [];

    frappe.container.page = wrapper;
    const lifecycle = api.bindActivationLifecycle(wrapper, {
        onActivate: () => events.push("activate"),
        onDeactivate: () => events.push("deactivate"),
    });

    assert.equal(lifecycle.isActive(), true, "mounting the current Frappe page must detect its active visit");
    assert.equal(harness.listenerCount(wrapper), 2, "one owner binds exactly one show and one hide listener");

    harness.trigger(wrapper, "show");
    assert.deepEqual(events, [], "duplicate show while already active must not start another refresh");

    frappe.container.page = otherPage;
    harness.trigger(wrapper, "hide");
    harness.trigger(wrapper, "hide");
    assert.deepEqual(events, ["deactivate"], "hide must deactivate exactly once without disposing the mount");
    assert.equal(lifecycle.isDisposed(), false);

    frappe.container.page = wrapper;
    harness.trigger(wrapper, "show");
    harness.trigger(wrapper, "show");
    assert.deepEqual(events, ["deactivate", "activate"], "a real revisit activates and refreshes exactly once");

    assert.equal(lifecycle.dispose(), true);
    assert.equal(lifecycle.dispose(), false, "dispose must be idempotent");
    assert.equal(harness.listenerCount(wrapper), 0, "dispose must remove owned listeners");
})();

(() => {
    const { api, frappe, harness } = loadRuntime();
    const wrapper = { _route: "factory-workforce" };
    let refreshes = 0;

    // The first show happened before an async bootstrap attached the helper, and
    // the user already left. `_route` proves that the next show is a real revisit.
    frappe.container.page = {};
    assert.equal(api.refreshOnRevisit(wrapper, () => { refreshes += 1; }), true);
    frappe.container.page = wrapper;
    harness.trigger(wrapper, "show");
    assert.equal(refreshes, 1, "late lifecycle installation must not swallow the first real revisit");
})();

(() => {
    const { api, frappe, harness } = loadRuntime();
    const wrapper = {};
    const calls = [];

    frappe.container.page = {};
    const first = api.bindActivationLifecycle(wrapper, { onActivate: () => calls.push("first") });
    const second = api.bindActivationLifecycle(wrapper, { onActivate: () => calls.push("second") });
    assert.equal(first.isDisposed(), true, "remount must dispose the previous activation owner");
    assert.equal(harness.listenerCount(wrapper), 2, "remount must not duplicate listeners");

    frappe.container.page = wrapper;
    harness.trigger(wrapper, "show");
    assert.deepEqual(calls, ["second"]);
    second.dispose();
})();

(() => {
    const { api, frappe } = loadRuntime();
    const wrapper = {};
    let oldDeactivations = 0;

    frappe.container.page = wrapper;
    const first = api.bindActivationLifecycle(wrapper, {
        onDeactivate: () => { oldDeactivations += 1; },
    });
    api.bindActivationLifecycle(wrapper, {});

    assert.equal(first.isDisposed(), true);
    assert.equal(oldDeactivations, 1, "replacing an active owner must invalidate its active visit");
})();

(() => {
    const { api } = loadRuntime({ cachedOldApi: true });
    assert.equal(
        typeof api.bindActivationLifecycle,
        "function",
        "a cached pre-activation helper must be upgraded instead of blocking the new contract"
    );
})();

console.log("Frappe page activation lifecycle simulation passed");
