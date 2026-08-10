"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

function deferred() {
    let resolve;
    let reject;
    const promise = new Promise((resolvePromise, rejectPromise) => {
        resolve = resolvePromise;
        reject = rejectPromise;
    });
    return { promise, resolve, reject };
}

function jqueryThenable(promise) {
    return {
        then(onFulfilled, onRejected) {
            return jqueryThenable(promise.then(onFulfilled, onRejected));
        },
        catch(onRejected) {
            return jqueryThenable(promise.catch(onRejected));
        },
    };
}

async function flushPromises() {
    await Promise.resolve();
    await Promise.resolve();
    await Promise.resolve();
}

(async () => {
    const calls = [];
    const events = [];
    const fakeWindow = {
        cur_frm: null,
        dispatchEvent(event) {
            events.push(event);
        },
        setInterval() {
            return 1;
        },
        clearInterval() {},
        setTimeout(callback) {
            callback();
            return 1;
        },
    };
    const fakeFrappe = {
        boot: { almdina_permissions: { version: 1, capabilities: {} } },
        session: { user: "Administrator" },
        almdina: {},
        provide() {},
        call() {
            const pending = deferred();
            calls.push(pending);
            return jqueryThenable(pending.promise);
        },
    };
    fakeWindow.frappe = fakeFrappe;
    const context = vm.createContext({
        window: fakeWindow,
        frappe: fakeFrappe,
        console,
        Promise,
        Object,
        Array,
        String,
        Number,
        Boolean,
        CustomEvent: class CustomEvent {
            constructor(type, options) {
                this.type = type;
                this.detail = options.detail;
            }
        },
    });
    const filename = path.resolve(__dirname, "../../public/js/permission_context.js");
    vm.runInContext(fs.readFileSync(filename, "utf8"), context);

    const first = fakeWindow.AlmdinaPermissions.refresh();
    calls[0].resolve({ message: { version: 2, capabilities: { dispatch_order: true } } });
    await first;
    assert.equal(fakeWindow.AlmdinaPermissions.version(), 2);
    assert.equal(events.at(-1).type, "almdina:permissions-updated");

    const second = fakeWindow.AlmdinaPermissions.refresh();
    assert.equal(calls.length, 2, "the in-flight cache must be released after a jqXHR-like request");
    calls[1].resolve({ message: { version: 3, capabilities: { dispatch_order: true } } });
    await second;
    await flushPromises();
    assert.equal(fakeWindow.AlmdinaPermissions.version(), 3);

    console.log("Permission context jqXHR compatibility simulation passed");
})().catch(error => {
    console.error(error);
    process.exitCode = 1;
});
