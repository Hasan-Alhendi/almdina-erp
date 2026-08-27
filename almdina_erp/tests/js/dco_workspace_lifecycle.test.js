"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

function source(relativePath) {
    return fs.readFileSync(path.resolve(__dirname, "../../", relativePath), "utf8");
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
    await Promise.resolve();
}

function makeWrapper() {
    const attributes = new Map();
    let markup = "";
    return {
        length: 1,
        attr(name, value) {
            if (value === undefined) return attributes.get(name);
            attributes.set(name, String(value));
            return this;
        },
        html(value) {
            if (value === undefined) return markup;
            markup = String(value);
            return this;
        },
    };
}

(async () => {
    const listeners = new Map();
    const formHooks = [];
    const frm = {
        doctype: "Door Cutting Order",
        doc: {
            doctype: "Door Cutting Order",
            name: "DCO-TEST-0001",
            pieces: [],
        },
        fields_dict: {
            plan_controls_intro: { $wrapper: makeWrapper() },
            cutting_plan_html: { $wrapper: makeWrapper() },
            order_cost_invoice_html: { $wrapper: makeWrapper() },
        },
        is_new() {
            return false;
        },
    };

    const fakeWindow = {
        cur_frm: frm,
        addEventListener(name, handler) {
            if (!listeners.has(name)) listeners.set(name, []);
            listeners.get(name).push(handler);
        },
        dispatchEvent(event) {
            for (const handler of listeners.get(event.type) || []) handler(event);
            return true;
        },
        requestAnimationFrame(callback) {
            callback();
            return 1;
        },
        setTimeout(callback) {
            callback();
            return 1;
        },
        clearTimeout() {},
        AlmdinaPermissions: {
            canDocument() {
                return true;
            },
            can() {
                return true;
            },
        },
        AlmdinaDocumentContext: {
            formIdentity(currentForm) {
                return `${currentForm.doctype}::${currentForm.doc.name}`;
            },
            capture(currentForm) {
                return Object.freeze({
                    identity: `${currentForm.doctype}::${currentForm.doc.name}`,
                    generation: 0,
                });
            },
            isCurrent(currentForm, token) {
                return token.identity === `${currentForm.doctype}::${currentForm.doc.name}`;
            },
            scheduleFrame(_frm, _key, callback) {
                callback();
                return 1;
            },
        },
    };

    const fakeFrappe = {
        boot: {},
        utils: {
            escape_html(value) {
                return String(value || "");
            },
        },
        ui: {
            form: {
                on(doctype, handlers) {
                    formHooks.push({ doctype, handlers });
                },
            },
        },
        msgprint() {},
    };
    fakeWindow.frappe = fakeFrappe;

    class CustomEvent {
        constructor(type, options = {}) {
            this.type = type;
            this.detail = options.detail;
        }
    }

    const context = vm.createContext({
        window: fakeWindow,
        document: { documentElement: { lang: "" } },
        frappe: fakeFrappe,
        console,
        Promise,
        Object,
        Array,
        Map,
        Set,
        String,
        Number,
        Boolean,
        JSON,
        Date,
        CustomEvent,
        structuredClone: global.structuredClone,
        __: value => String(value),
    });

    vm.runInContext(
        source("public/js/door_cutting_order/core/door_cutting_order_workspace_store.js"),
        context,
        { filename: "door_cutting_order_workspace_store.js" }
    );

    const planFlights = [deferred(), deferred(), deferred()];
    let planCalls = 0;
    fakeWindow.AlmdinaPlanWorkspaceAPI = {
        load() {
            const flight = planFlights[planCalls];
            planCalls += 1;
            if (!flight) return Promise.reject(new Error("unexpected plan request"));
            return flight.promise;
        },
    };
    fakeWindow.AlmdinaPlanTabsUX = {
        shouldShowPlanTabs() {
            return true;
        },
        renderDualTabs() {
            return true;
        },
        printActivePlan() {
            return true;
        },
        afterRender() {
            return true;
        },
    };

    vm.runInContext(
        source("public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_workspace_state.js"),
        context,
        { filename: "door_cutting_order_plan_workspace_state.js" }
    );
    vm.runInContext(
        source("public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_workspace_presenter_adapter.js"),
        context,
        { filename: "door_cutting_order_plan_workspace_presenter_adapter.js" }
    );

    const costFlight = deferred();
    let costCalls = 0;
    fakeWindow.AlmdinaCostWorkspaceAPI = {
        load() {
            costCalls += 1;
            return costFlight.promise;
        },
    };
    fakeWindow.AlmdinaOrderCostUX = {
        render() {
            return true;
        },
        refreshInvoiceSection() {
            return true;
        },
        invoiceLines() {
            return [];
        },
        invoiceTotal() {
            return 0;
        },
        quoteTotal() {
            return 0;
        },
    };

    vm.runInContext(
        source("public/js/door_cutting_order/costing/door_cutting_order_cost_workspace_state.js"),
        context,
        { filename: "door_cutting_order_cost_workspace_state.js" }
    );
    vm.runInContext(
        source("public/js/door_cutting_order/costing/door_cutting_order_cost_workspace_presenter_adapter.js"),
        context,
        { filename: "door_cutting_order_cost_workspace_presenter_adapter.js" }
    );

    const planState = fakeWindow.AlmdinaPlanWorkspaceState;
    const costState = fakeWindow.AlmdinaCostWorkspaceState;

    // Loading state is dispatched synchronously. The presenters therefore run
    // during load() itself; this used to recurse into load() before the in-flight
    // promise existed and ended with Maximum call stack size exceeded.
    const firstPlan = planState.load(frm);
    const firstCost = costState.load(frm);
    await flushPromises();
    assert.equal(planCalls, 1, "plan loading render must not create a second request");
    assert.equal(costCalls, 1, "cost loading render must not create a second request");

    // A permission/lifecycle refresh while the same request is slow must join the
    // current flight instead of creating a duplicate network request.
    fakeWindow.dispatchEvent(new CustomEvent("almdina:permissions-updated", { detail: {} }));
    await flushPromises();
    assert.equal(planCalls, 1, "forced plan refresh must join a current fresh flight");
    assert.equal(costCalls, 1, "forced cost refresh must join a current fresh flight");

    planFlights[0].resolve({
        plans: { system_draft: null, uploaded_draft: null, approved: null },
        approved_plan: null,
        editable_settings: null,
    });
    costFlight.resolve({ order: {}, pieces: [] });
    await Promise.all([firstPlan, firstCost]);
    await flushPromises();
    assert.equal(planState.snapshot(frm).status, "ready");
    assert.equal(costState.snapshot(frm).status, "ready");
    assert.equal(planCalls, 1);
    assert.equal(costCalls, 1);

    // Preserve force semantics after a real invalidation. A force request that
    // arrives while an older read is in flight waits for it, notices that its
    // request generation was invalidated, and performs exactly one fresh follow-up.
    const secondPlan = planState.load(frm, { force: true });
    await flushPromises();
    assert.equal(planCalls, 2);
    planState.invalidate(frm, "test_dependency_changed");
    const forcedAfterInvalidation = planState.load(frm, { force: true });
    await flushPromises();
    assert.equal(planCalls, 2, "invalidated force must not race the old flight");

    planFlights[1].resolve({
        plans: { system_draft: null, uploaded_draft: null, approved: null },
        approved_plan: null,
        editable_settings: null,
    });
    await secondPlan;
    await flushPromises();
    assert.equal(planCalls, 3, "stale old flight must be followed by one fresh request");

    planFlights[2].resolve({
        plans: { system_draft: null, uploaded_draft: null, approved: null },
        approved_plan: null,
        editable_settings: null,
    });
    await forcedAfterInvalidation;
    assert.equal(planState.snapshot(frm).status, "ready");
    assert.equal(planState.snapshot(frm).freshness, "fresh");

    // Frappe v16 can expose a jqXHR-like thenable without native .finally().
    // Order defaults must normalize that transport before attaching finally.
    const edgeCalls = [];
    fakeFrappe.call = function () {
        const pending = deferred();
        edgeCalls.push(pending);
        return jqueryThenable(pending.promise);
    };
    vm.runInContext(
        source("public/js/door_cutting_order/order_entry/door_cutting_order_defaults.js"),
        context,
        { filename: "door_cutting_order_defaults.js" }
    );

    const edgeRequest = fakeWindow.AlmdinaOrderEdgeOptions.load(frm);
    assert.equal(edgeCalls.length, 1);
    edgeCalls[0].resolve({
        message: {
            options: [{ name: "EDGE-1", edge_type_name: "2cm" }],
            include_financial: false,
        },
    });
    await edgeRequest;
    assert.equal(frm._almdina_safe_edge_options_loading, null);
    assert.equal(fakeWindow.AlmdinaOrderEdgeOptions.snapshot(frm).options.length, 1);

    frm._almdina_safe_edge_options_loaded = false;
    const edgeRetry = fakeWindow.AlmdinaOrderEdgeOptions.load(frm);
    assert.equal(edgeCalls.length, 2, "jqXHR normalization must release the in-flight cache");
    edgeCalls[1].resolve({ message: { options: [], include_financial: false } });
    await edgeRetry;
    assert.equal(frm._almdina_safe_edge_options_loading, null);

    assert.ok(formHooks.length >= 3, "form lifecycle hooks should remain registered");
    console.log("DCO workspace lifecycle simulation passed");
})().catch(error => {
    console.error(error);
    process.exitCode = 1;
});
