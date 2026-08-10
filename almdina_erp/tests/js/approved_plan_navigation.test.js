"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

function source(filename) {
    return fs.readFileSync(path.resolve(__dirname, "../../public/js", filename), "utf8");
}

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
    const handlers = {};
    const calls = [];
    const fakeWindow = {
        cur_frm: null,
        clearTimeout() {},
        AlmdinaPermissions: {
            canDocument() {
                return true;
            },
        },
    };
    const fakeFrappe = {
        ui: {
            form: {
                on(doctype, events) {
                    handlers[doctype] = handlers[doctype] || {};
                    Object.assign(handlers[doctype], events);
                },
            },
        },
        call(options) {
            const pending = deferred();
            calls.push({ options, pending });
            return jqueryThenable(pending.promise);
        },
        utils: { escape_html: value => String(value) },
    };
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
        Set,
        Map,
        __: value => value,
        setTimeout() {
            return 1;
        },
    });
    vm.runInContext(source("door_cutting_order_document_context.js"), context);
    vm.runInContext(source("door_cutting_order_plan_tabs_ux.js"), context);

    const frm = {
        doctype: "Door Cutting Order",
        doc: {
            doctype: "Door Cutting Order",
            name: "DCO-A",
            approved_plan: "PLAN-A",
        },
        fields_dict: {},
    };
    fakeWindow.cur_frm = frm;
    fakeWindow.AlmdinaDocumentContext.synchronize(frm);

    const stale = fakeWindow.AlmdinaPlanTabsUX.ensureApprovedPlanLoaded(frm);
    assert.equal(calls[0].options.args.order_name, "DCO-A");
    frm.doc = {
        doctype: "Door Cutting Order",
        name: "DCO-B",
        approved_plan: "PLAN-B",
    };
    fakeWindow.AlmdinaDocumentContext.synchronize(frm);
    calls[0].pending.resolve({ message: { snapshot_json: '{"sheets":[{"source":"A"}]}' } });
    assert.equal(await stale, null);
    assert.equal(frm.__almdina_approved_plan_snapshot, null);

    const current = fakeWindow.AlmdinaPlanTabsUX.ensureApprovedPlanLoaded(frm);
    assert.equal(calls[1].options.args.order_name, "DCO-B");
    calls[1].pending.resolve({ message: { snapshot_json: '{"sheets":[{"source":"B"}]}' } });
    await current;
    await flushPromises();
    assert.equal(frm.__almdina_approved_plan_order, "DCO-B");
    assert.equal(frm.__almdina_approved_plan_snapshot.sheets[0].source, "B");

    console.log("Approved cutting-plan navigation isolation simulation passed");
})().catch(error => {
    console.error(error);
    process.exitCode = 1;
});
