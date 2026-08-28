"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(
    path.resolve(__dirname, "../../public/js/door_cutting_order/core/order_lifecycle.js"),
    "utf8"
);

function jqueryThenable(promise) {
    return {
        then(onFulfilled, onRejected) {
            return jqueryThenable(promise.then(onFulfilled, onRejected));
        },
        catch(onRejected) {
            return jqueryThenable(promise.catch(onRejected));
        },
        // Deliberately no .finally(): this matches the Frappe jqXHR-like
        // transport shape that triggered the production regression.
    };
}

function makeForm() {
    const added = [];
    return {
        doctype: "Door Cutting Order",
        doc: {
            name: "DCO-JQUERY-THENABLE-001",
            status: "At Drawing",
            docstatus: 0,
        },
        added,
        is_new() {
            return false;
        },
        add_custom_button(label, handler, group) {
            added.push({ label, handler, group });
        },
        remove_custom_button(label, group) {
            for (let index = added.length - 1; index >= 0; index -= 1) {
                const button = added[index];
                if (button.label !== label) continue;
                if (group !== undefined && button.group !== group) continue;
                added.splice(index, 1);
            }
        },
        reload_doc() {
            return Promise.resolve();
        },
    };
}

(async () => {
    const calls = [];
    let settledSurfaces = 0;
    const lifecycle = {
        order_name: "DCO-JQUERY-THENABLE-001",
        editable: false,
        actions: {
            return_to_draft: { allowed: true },
            cancel: { allowed: false },
        },
    };
    const fakeWindow = {
        AlmdinaPermissions: {
            can() {
                return true;
            },
        },
        AlmdinaDocumentContext: {
            capture(frm) {
                return { name: frm.doc.name };
            },
            isCurrent(frm, identity) {
                return frm.doc.name === identity.name;
            },
            settleSurfaces() {
                settledSurfaces += 1;
            },
        },
    };
    const fakeFrappe = {
        almdina: {},
        ui: {
            form: {
                on() {},
            },
        },
        provide(namespace) {
            assert.equal(namespace, "frappe.almdina");
            this.almdina = this.almdina || {};
        },
        call(options) {
            calls.push(options);
            return jqueryThenable(Promise.resolve({ message: lifecycle }));
        },
        show_alert() {},
        set_route() {},
        confirm() {},
        prompt() {},
    };
    const context = vm.createContext({
        window: fakeWindow,
        frappe: fakeFrappe,
        console,
        Promise,
        Object,
        Number,
        String,
        Boolean,
        Set,
        setTimeout,
        clearTimeout,
        __: value => value,
    });

    vm.runInContext(source, context, { filename: "order_lifecycle.js" });

    const frm = makeForm();
    const first = await fakeWindow.AlmdinaOrderLifecycleUX.loadContext(frm);
    assert.equal(first.order_name, lifecycle.order_name);
    assert.equal(frm.__almdina_lifecycle_context.order_name, lifecycle.order_name);
    assert.equal(frm.__almdinaLifecycleContextPending, false);
    assert.equal(frm.__almdinaLifecycleContextPromise, null);
    assert.equal(frm.__almdinaLifecycleContextToken, null);
    assert.equal(calls.length, 1);
    assert.equal(settledSurfaces, 1);

    // A settled jqXHR-like request must release the single-flight barrier so a
    // later permissions refresh can request fresh lifecycle context.
    await fakeWindow.AlmdinaOrderLifecycleUX.loadContext(frm);
    assert.equal(calls.length, 2);
    assert.equal(settledSurfaces, 2);

    console.log("Order lifecycle jqXHR-like thenable simulation passed");
})().catch(error => {
    console.error(error);
    process.exitCode = 1;
});
