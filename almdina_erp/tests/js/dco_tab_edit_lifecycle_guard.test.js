"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

function source(relativePath) {
    return fs.readFileSync(path.resolve(__dirname, "../../", relativePath), "utf8");
}

function makeTab(fieldname, activeState) {
    let activationCount = 0;
    function nativeSetActive() {
        activationCount += 1;
        activeState.fieldname = fieldname;
        return `activated:${fieldname}`;
    }
    return {
        df: { fieldname },
        set_active: nativeSetActive,
        nativeSetActive,
        is_active() {
            return activeState.fieldname === fieldname;
        },
        get activationCount() {
            return activationCount;
        },
    };
}

function verifyNativeTabLifecycleGuard() {
    const formHandlers = {};
    const messages = [];
    const cleanups = new Map();
    const activeState = { fieldname: "results_tab" };
    let editingKind = "plan";
    let scheduleCount = 0;

    const makeTabs = () => [
        makeTab("order_tab", activeState),
        makeTab("results_tab", activeState),
        makeTab("cost_tab", activeState),
    ];

    const frm = {
        doctype: "Door Cutting Order",
        doc: { doctype: "Door Cutting Order", name: "DCO-TAB-GUARD-1" },
        layout: { tabs: makeTabs() },
        get_active_tab() {
            return this.layout.tabs.find((tab) => tab.df.fieldname === activeState.fieldname) || null;
        },
    };

    const fakeWindow = {
        AlmdinaPageEditActionUX: {
            activeEditingKind() {
                return editingKind;
            },
            schedule() {
                scheduleCount += 1;
            },
        },
        AlmdinaDocumentContext: {
            registerCleanup(_frm, key, cleanup) {
                const previous = cleanups.get(key);
                if (previous) previous();
                cleanups.set(key, cleanup);
                return true;
            },
        },
    };

    const fakeFrappe = {
        ui: {
            form: {
                on(doctype, handlers) {
                    assert.equal(doctype, "Door Cutting Order");
                    Object.assign(formHandlers, handlers);
                },
            },
        },
        msgprint(payload) {
            messages.push(payload);
        },
    };

    const context = vm.createContext({
        window: fakeWindow,
        frappe: fakeFrappe,
        console,
        Object,
        Array,
        Set,
        String,
        Boolean,
        __: value => String(value),
    });

    vm.runInContext(
        source("public/js/door_cutting_order/core/door_cutting_order_tab_edit_lifecycle_guard.js"),
        context,
        { filename: "door_cutting_order_tab_edit_lifecycle_guard.js" }
    );

    assert.equal(typeof formHandlers.refresh, "function");
    formHandlers.refresh(frm);

    for (const scenario of [
        { kind: "plan", current: "results_tab", target: "order_tab" },
        { kind: "cost", current: "cost_tab", target: "results_tab" },
        { kind: "order", current: "order_tab", target: "cost_tab" },
    ]) {
        editingKind = scenario.kind;
        activeState.fieldname = scenario.current;
        messages.length = 0;
        const target = frm.layout.tabs.find((tab) => tab.df.fieldname === scenario.target);
        const beforeCount = target.activationCount;
        const result = target.set_active();

        assert.equal(result, false, `${scenario.kind} edit must reject native Tab.set_active()`);
        assert.equal(target.activationCount, beforeCount, "blocked navigation must not reach Frappe activation");
        assert.equal(activeState.fieldname, scenario.current, "blocked navigation must not mutate active tab state");
        assert.equal(messages.length, 1, "blocked navigation should show exactly one message");
        assert.equal(messages[0].title, "التعديل ما زال مفتوحًا");
        assert.match(messages[0].message, /احفظ أو ألغِ/);
    }

    editingKind = "plan";
    activeState.fieldname = "results_tab";
    messages.length = 0;
    const current = frm.layout.tabs.find((tab) => tab.df.fieldname === "results_tab");
    const currentResult = current.set_active();
    assert.equal(currentResult, "activated:results_tab", "re-activating the current tab remains harmless");
    assert.equal(messages.length, 0);

    editingKind = null;
    const cost = frm.layout.tabs.find((tab) => tab.df.fieldname === "cost_tab");
    const allowedResult = cost.set_active();
    assert.equal(allowedResult, "activated:cost_tab");
    assert.equal(activeState.fieldname, "cost_tab");
    assert.ok(scheduleCount >= 2, "allowed native activations should reconcile the page coordinator");

    editingKind = "plan";
    activeState.fieldname = "results_tab";
    const oldTabs = frm.layout.tabs;
    frm.layout.tabs = makeTabs();
    formHandlers.refresh(frm);

    oldTabs.forEach((tab) => {
        assert.equal(tab.set_active, tab.nativeSetActive, "rebuilt layouts must release guards from retired Tab instances");
    });
    frm.layout.tabs.forEach((tab) => {
        assert.notEqual(tab.set_active, tab.nativeSetActive, "rebuilt layouts must guard every new top-level DCO Tab instance");
    });

    messages.length = 0;
    const rebuiltOrder = frm.layout.tabs.find((tab) => tab.df.fieldname === "order_tab");
    assert.equal(rebuiltOrder.set_active(), false);
    assert.equal(messages.length, 1);

    const cleanup = cleanups.get("tab-edit-lifecycle-guard");
    assert.equal(typeof cleanup, "function");
    cleanup();
    frm.layout.tabs.forEach((tab) => {
        assert.equal(tab.set_active, tab.nativeSetActive, "document cleanup must restore Frappe's original Tab methods");
    });
}

verifyNativeTabLifecycleGuard();
console.log("DCO native tab edit lifecycle guard simulation passed");
