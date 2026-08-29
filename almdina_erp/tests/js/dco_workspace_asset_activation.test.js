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

async function flushPromises() {
    await Promise.resolve();
    await Promise.resolve();
    await Promise.resolve();
}

(async () => {
    const order = [];
    const formHooks = [];
    let activeFieldname = "results_tab";
    const frm = {
        doctype: "Door Cutting Order",
        doc: { name: "DCO-TEST-0001" },
        // Reproduce Frappe v16 runtime behavior seen in production: the canonical
        // form API already reports Plan while layout.current_tab still points to
        // the previously visited Cost tab.
        get_active_tab() {
            return { df: { fieldname: activeFieldname } };
        },
        layout: { current_tab: { df: { fieldname: "cost_tab" } } },
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
        AlmdinaPageEditActionUX: {
            sync() {
                assert.ok(
                    fakeWindow.AlmdinaPlanEditSessionUX,
                    "Plan toolbar sync must run only after the lazy edit-session API exists"
                );
                order.push("edit:sync");
                return true;
            },
        },
        AlmdinaWorkspaceSyncCoordinator: {
            activationFields() {
                return ["results_tab", "cost_tab"];
            },
            activateCurrent(currentForm) {
                order.push("workspace:activate");
                const fieldname = currentForm.get_active_tab().df.fieldname;
                return Promise.resolve([fieldname === "cost_tab" ? "cost" : "plan"]);
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
    const lifecycleHook = formHooks.find(entry =>
        entry.doctype === "Door Cutting Order"
        && entry.handlers
        && typeof entry.handlers.on_tab_change === "function"
    );
    assert.ok(lifecycle);
    assert.ok(lifecycleHook, "DCO workspace lifecycle must subscribe to Frappe on_tab_change");
    assert.equal(frm.layout.current_tab.df.fieldname, "cost_tab");
    assert.equal(frm.get_active_tab().df.fieldname, "results_tab");

    const activation = lifecycle.activate(frm);
    await Promise.resolve();
    assert.deepEqual(
        order,
        ["assets:results_tab"],
        "Plan activation must follow get_active_tab(), not stale layout.current_tab"
    );

    // Simulate the Plan edit-session global appearing when the cold lazy bundle
    // finishes evaluating. The eager page toolbar must then be re-evaluated before
    // normal Plan workspace activation continues.
    fakeWindow.AlmdinaPlanEditSessionUX = {
        canEditPlanSettings() {
            return true;
        },
    };
    planAssets.resolve(true);
    assert.deepEqual(await activation, ["plan"]);
    assert.deepEqual(order, [
        "assets:results_tab",
        "edit:sync",
        "workspace:activate",
    ]);

    // Production regression: delegated DOM click handling did not reliably see
    // Cost tab activation even though Frappe had already updated get_active_tab().
    // The host's official on_tab_change hook must start the lazy Cost bundle.
    order.length = 0;
    const costAssets = deferred();
    fakeWindow.AlmdinaDcoWorkspaceAssetRegistry.ensureForTab = fieldname => {
        order.push(`assets:${fieldname}`);
        return costAssets.promise;
    };
    fakeWindow.AlmdinaOrderPermissionRefreshUX = {
        applySurfaces() {
            order.push("surfaces:apply");
        },
    };
    activeFieldname = "cost_tab";
    frm.layout.current_tab.df.fieldname = "cost_tab";
    lifecycleHook.handlers.on_tab_change(frm);
    await Promise.resolve();
    assert.deepEqual(
        order,
        ["assets:cost_tab"],
        "Frappe on_tab_change must start the Cost lazy bundle without manual activation"
    );

    // Simulate the globals appearing only when the cold bundle finishes evaluating.
    fakeWindow.AlmdinaFinancialDocuments = {
        apply() {
            order.push("financial:apply");
        },
    };
    fakeWindow.AlmdinaCustomerInvoiceToolbarUX = {
        install() {
            order.push("invoice:install");
        },
    };
    costAssets.resolve(true);
    await flushPromises();
    assert.deepEqual(order, [
        "assets:cost_tab",
        "surfaces:apply",
        "financial:apply",
        "invoice:install",
        "workspace:activate",
    ]);

    // If the user switches tabs while a cold bundle is downloading, keep the
    // downloaded files cached but reject the stale workspace activation using the
    // canonical active-tab API even if layout.current_tab still says Plan.
    order.length = 0;
    const staleAssets = deferred();
    fakeWindow.AlmdinaDcoWorkspaceAssetRegistry.ensureForTab = fieldname => {
        order.push(`assets:${fieldname}`);
        return staleAssets.promise;
    };
    activeFieldname = "results_tab";
    frm.layout.current_tab.df.fieldname = "cost_tab";
    const staleActivation = lifecycle.activate(frm);
    await Promise.resolve();
    activeFieldname = "order_tab";
    frm.layout.current_tab.df.fieldname = "results_tab";
    staleAssets.resolve(true);
    assert.deepEqual(Array.from(await staleActivation), []);
    assert.deepEqual(order, ["assets:results_tab"], "stale tab must not start a Plan RPC or toolbar sync");

    assert.ok(formHooks.some(entry => entry.doctype === "Door Cutting Order"));
    console.log("DCO workspace asset activation simulation passed");
})().catch(error => {
    console.error(error);
    process.exitCode = 1;
});
