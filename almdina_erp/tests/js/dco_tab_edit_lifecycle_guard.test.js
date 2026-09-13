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
    const attributes = new Map([
        ["data-toggle", "tab"],
        ["data-fieldname", fieldname],
    ]);
    const navLink = {
        length: 1,
        attr(name, value) {
            if (arguments.length > 1) {
                attributes.set(name, value);
                return this;
            }
            return attributes.has(name) ? attributes.get(name) : undefined;
        },
        removeAttr(name) {
            attributes.delete(name);
            return this;
        },
    };

    function nativeSetActive() {
        activationCount += 1;
        activeState.fieldname = fieldname;
        return `activated:${fieldname}`;
    }

    return {
        df: { fieldname },
        set_active: nativeSetActive,
        nativeSetActive,
        tab_link: {
            find(selector) {
                assert.equal(selector, ".nav-link[data-fieldname]");
                return navLink;
            },
        },
        is_active() {
            return activeState.fieldname === fieldname;
        },
        get activationCount() {
            return activationCount;
        },
        get dataToggle() {
            return navLink.attr("data-toggle");
        },
    };
}

function simulateBootstrapDataApi(tab, activeState) {
    if (tab.dataToggle !== "tab") return false;
    activeState.fieldname = tab.df.fieldname;
    return true;
}

function verifyNativeTabLifecycleGuard() {
    const formHandlers = {};
    const messages = [];
    const cleanups = new Map();
    const activeState = { fieldname: "results_tab" };
    let editingKind = "plan";
    let scheduleCount = 0;
    let legacyRemoveCount = 0;

    const makeTabs = () => [
        makeTab("order_tab", activeState),
        makeTab("results_tab", activeState),
        makeTab("cost_tab", activeState),
    ];

    const legacyHandler = () => {};
    const legacyRoot = {
        removeEventListener(name, handler, capture) {
            assert.equal(name, "click");
            assert.equal(handler, legacyHandler);
            assert.equal(capture, true);
            legacyRemoveCount += 1;
        },
    };

    const frm = {
        doctype: "Door Cutting Order",
        doc: { doctype: "Door Cutting Order", name: "DCO-TAB-GUARD-1" },
        layout: { tabs: makeTabs() },
        __almdinaPageEditTabListenerRoot: legacyRoot,
        __almdinaPageEditTabListenerHandler: legacyHandler,
        get_active_tab() {
            return this.layout.tabs.find((tab) => tab.df.fieldname === activeState.fieldname) || null;
        },
    };

    const fakeWindow = {
        AlmdinaDcoEditSessionCoordinator: {
            activeKind() {
                return editingKind;
            },
        },
        AlmdinaPageEditActionUX: {
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
    assert.equal(legacyRemoveCount, 1, "native lifecycle owner must retire the old PageEditActionUX click guard");
    assert.equal(frm.__almdinaPageEditTabListenerRoot, null);
    assert.equal(frm.__almdinaPageEditTabListenerHandler, null);
    frm.layout.tabs.forEach((tab) => {
        assert.equal(
            tab.dataToggle,
            undefined,
            "guarded DCO tabs must disable Bootstrap data-api auto activation so Frappe set_active is the only switch boundary"
        );
    });

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

        // Frappe's direct click handler calls the guarded instance method.
        const result = target.set_active();
        assert.equal(result, false, `${scenario.kind} edit must reject native Tab.set_active()`);
        assert.equal(target.activationCount, beforeCount, "blocked navigation must not reach Frappe activation");
        assert.equal(activeState.fieldname, scenario.current, "blocked navigation must not mutate active tab state");
        assert.equal(messages.length, 1, "blocked navigation should show exactly one message");
        assert.equal(messages[0].title, "التعديل ما زال مفتوحًا");
        assert.match(messages[0].message, /احفظ أو ألغِ/);

        // Bootstrap's delegated data-api used to be a second click path because
        // Frappe renders data-toggle=tab on the same button. The lifecycle owner
        // removes that hook, so it cannot visually activate the target afterwards.
        assert.equal(simulateBootstrapDataApi(target, activeState), false);
        assert.equal(activeState.fieldname, scenario.current);
        assert.equal(messages.length, 1, "the removed Bootstrap path must not create a duplicate warning");
    }

    editingKind = "plan";
    activeState.fieldname = "results_tab";
    messages.length = 0;
    const current = frm.layout.tabs.find((tab) => tab.df.fieldname === "results_tab");
    const currentResult = current.set_active();
    assert.equal(currentResult, "activated:results_tab", "re-activating the current tab remains harmless");
    assert.equal(messages.length, 0);

    // Save/Cancel closes the aggregate session; Frappe's own listener still switches
    // tabs normally even though Bootstrap auto-activation remains disabled.
    editingKind = null;
    const cost = frm.layout.tabs.find((tab) => tab.df.fieldname === "cost_tab");
    const allowedResult = cost.set_active();
    assert.equal(allowedResult, "activated:cost_tab");
    assert.equal(activeState.fieldname, "cost_tab");
    assert.equal(cost.dataToggle, undefined);
    assert.ok(scheduleCount >= 2, "allowed native activations should reconcile the page coordinator");

    editingKind = "plan";
    activeState.fieldname = "results_tab";
    const oldTabs = frm.layout.tabs;
    frm.layout.tabs = makeTabs();
    formHandlers.refresh(frm);

    oldTabs.forEach((tab) => {
        assert.equal(tab.set_active, tab.nativeSetActive, "rebuilt layouts must release guards from retired Tab instances");
        assert.equal(tab.dataToggle, "tab", "retired Tab markup must regain its original Bootstrap attribute");
    });
    frm.layout.tabs.forEach((tab) => {
        assert.notEqual(tab.set_active, tab.nativeSetActive, "rebuilt layouts must guard every new top-level DCO Tab instance");
        assert.equal(tab.dataToggle, undefined, "rebuilt guarded Tabs must also suppress Bootstrap auto activation");
    });

    messages.length = 0;
    const rebuiltOrder = frm.layout.tabs.find((tab) => tab.df.fieldname === "order_tab");
    assert.equal(rebuiltOrder.set_active(), false);
    assert.equal(simulateBootstrapDataApi(rebuiltOrder, activeState), false);
    assert.equal(messages.length, 1);

    const cleanup = cleanups.get("tab-edit-lifecycle-guard");
    assert.equal(typeof cleanup, "function");
    cleanup();
    frm.layout.tabs.forEach((tab) => {
        assert.equal(tab.set_active, tab.nativeSetActive, "document cleanup must restore Frappe's original Tab methods");
        assert.equal(tab.dataToggle, "tab", "document cleanup must restore Frappe's original tab markup");
    });
}

verifyNativeTabLifecycleGuard();
console.log("DCO semantic tab edit lifecycle guard simulation passed");
