"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(
    path.resolve(
        __dirname,
        "../../public/js/door_cutting_order/core/door_cutting_order_workspace_activation_lifecycle.js"
    ),
    "utf8"
);

function deferred() {
    let resolve;
    let reject;
    const promise = new Promise((resolvePromise, rejectPromise) => {
        resolve = resolvePromise;
        reject = rejectPromise;
    });
    return { promise, resolve, reject };
}

(async () => {
    const order = [];
    const formHooks = [];
    const frm = {
        doctype: "Door Cutting Order",
        doc: { name: "DCO-TEST-0001" },
        layout: { current_tab: { df: { fieldname: "results_tab" } } },
        wrapper: {
            nodeType: 1,
            addEventListener() {},
            removeEventListener() {},
        },
    };
    const planAssets = deferred();

    const fakeWindow = {
        cur_frm: frm,
        addEventListener() {},
        requestAnimationFrame(callback) {
            callback();
            return 1;
        },
        setTimeout(callback) {
            callback();
            return 1;
        },
        AlmdinaDocumentContext: {
            capture(currentForm) {
                return Object.freeze({ identity: currentForm.doc.name, generation: 0 });
            },
            isCurrent(currentForm, token) {
                return token.identity === currentForm.doc.name;
            },
            scheduleFrame(_frm, _key, callback) {
                callback();
                return 1;
            },
            registerCleanup() {
                return true;
            },
        },
        AlmdinaDcoWorkspaceAssetRegistry: {
            activationFields() {
                return ["results_tab", "cost_tab"];
            },
            ensureForTab(fieldname) {
                order.push(`assets:${fieldname}`);
                if (fieldname === "results_tab") return planAssets.promise;
                return Promise.resolve(false);
            },
        },
        AlmdinaWorkspaceSyncCoordinator: {
            activationFields() {
                return ["results_tab", "cost_tab"];
            },
            activateCurrent() {
                order.push("workspace:activate");
                return Promise.resolve(["plan"]);
            },
        },
    };

    const fakeFrappe = {
        ui: {
            form: {
                on(doctype, handlers) {
                    formHooks.push({ doctype, handlers });
                },
            },
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
        Set,
        String,
    });
    vm.runInContext(source, context, {
        filename: "door_cutting_order_workspace_activation_lifecycle.js",
    });

    const lifecycle = fakeWindow.AlmdinaDcoWorkspaceActivationLifecycle;
    assert.ok(lifecycle);
    const activation = lifecycle.activate(frm);
    await Promise.resolve();
    assert.deepEqual(order, ["assets:results_tab"], "Plan data must wait for its UI bundle");

    planAssets.resolve(true);
    assert.deepEqual(await activation, ["plan"]);
    assert.deepEqual(order, ["assets:results_tab", "workspace:activate"]);

    // If the user switches tabs while a cold bundle is downloading, keep the
    // downloaded files cached but reject the stale workspace activation.
    order.length = 0;
    const staleAssets = deferred();
    fakeWindow.AlmdinaDcoWorkspaceAssetRegistry.ensureForTab = fieldname => {
        order.push(`assets:${fieldname}`);
        return staleAssets.promise;
    };
    frm.layout.current_tab.df.fieldname = "results_tab";
    const staleActivation = lifecycle.activate(frm);
    await Promise.resolve();
    frm.layout.current_tab.df.fieldname = "order_tab";
    staleAssets.resolve(true);
    assert.deepEqual(await staleActivation, []);
    assert.deepEqual(order, ["assets:results_tab"], "stale tab must not start a Plan RPC");

    assert.ok(formHooks.some(entry => entry.doctype === "Door Cutting Order"));
    console.log("DCO workspace asset activation simulation passed");
})().catch(error => {
    console.error(error);
    process.exitCode = 1;
});
