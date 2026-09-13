"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

function source(relativePath) {
    return fs.readFileSync(path.resolve(__dirname, "../../", relativePath), "utf8");
}

function makeControl(fieldname) {
    const attributes = new Map([
        ["data-toggle", "tab"],
        ["data-fieldname", fieldname],
    ]);
    const properties = new Map([["disabled", false]]);
    const classes = new Set(["nav-link"]);
    return {
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
        prop(name, value) {
            if (arguments.length > 1) {
                properties.set(name, value);
                return this;
            }
            return properties.get(name);
        },
        hasClass(name) {
            return classes.has(name);
        },
        addClass(name) {
            classes.add(name);
            return this;
        },
        removeClass(name) {
            classes.delete(name);
            return this;
        },
    };
}

function makeTab(fieldname, activeState) {
    let activationCount = 0;
    const control = makeControl(fieldname);

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
                return control;
            },
        },
        is_active() {
            return activeState.fieldname === fieldname;
        },
        get activationCount() {
            return activationCount;
        },
        get dataToggle() {
            return control.attr("data-toggle");
        },
        get disabled() {
            return Boolean(control.prop("disabled"));
        },
        get ariaDisabled() {
            return control.attr("aria-disabled");
        },
        get tabIndex() {
            return control.attr("tabindex");
        },
        get title() {
            return control.attr("title");
        },
        get lockedClass() {
            return control.hasClass("dco-edit-navigation-locked");
        },
    };
}

function simulateNativeUserClick(tab) {
    if (tab.disabled) return false;
    return tab.set_active();
}

function simulateBootstrapDataApi(tab, activeState) {
    if (tab.disabled || tab.dataToggle !== "tab") return false;
    activeState.fieldname = tab.df.fieldname;
    return true;
}

function verifyEditOwnerNavigationLock() {
    const formHandlers = {};
    const messages = [];
    const cleanups = new Map();
    const activeState = { fieldname: "order_tab" };
    let editingKind = null;
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
    assert.equal(typeof formHandlers.almdina_edit_session_changed, "function");
    assert.equal(typeof formHandlers.on_tab_change, "function");

    formHandlers.refresh(frm);
    assert.equal(legacyRemoveCount, 1, "semantic owner must retire the historical click interceptor");
    assert.equal(frm.__almdinaPageEditTabListenerRoot, null);
    assert.equal(frm.__almdinaPageEditTabListenerHandler, null);
    frm.layout.tabs.forEach((tab) => {
        assert.equal(tab.dataToggle, undefined, "Bootstrap data-api must not compete with Frappe set_active");
        assert.equal(tab.disabled, false, "tabs remain native while no edit session owns navigation");
    });

    const scenarios = [
        { kind: "order", owner: "order_tab", blocked: ["results_tab", "cost_tab"] },
        { kind: "plan", owner: "results_tab", blocked: ["order_tab", "cost_tab"] },
        { kind: "cost", owner: "cost_tab", blocked: ["order_tab", "results_tab"] },
    ];

    for (const scenario of scenarios) {
        editingKind = scenario.kind;
        activeState.fieldname = scenario.owner;
        messages.length = 0;
        formHandlers.almdina_edit_session_changed(frm);

        const owner = frm.layout.tabs.find((tab) => tab.df.fieldname === scenario.owner);
        assert.equal(owner.disabled, false, `${scenario.kind} owner tab must remain available`);
        assert.equal(owner.lockedClass, false);

        for (const fieldname of scenario.blocked) {
            const target = frm.layout.tabs.find((tab) => tab.df.fieldname === fieldname);
            assert.equal(target.disabled, true, `${scenario.kind} edit must natively disable ${fieldname}`);
            assert.equal(target.ariaDisabled, "true");
            assert.equal(target.tabIndex, "-1");
            assert.equal(target.lockedClass, true);
            assert.match(target.title, /احفظ أو ألغِ/);

            const beforeCount = target.activationCount;
            assert.equal(simulateNativeUserClick(target), false, "disabled user click must not reach Frappe");
            assert.equal(target.activationCount, beforeCount);
            assert.equal(activeState.fieldname, scenario.owner);
            assert.equal(simulateBootstrapDataApi(target, activeState), false, "Bootstrap path must remain closed");
            assert.equal(activeState.fieldname, scenario.owner);

            const programmatic = target.set_active();
            assert.equal(programmatic, false, "programmatic activation must also be rejected");
            assert.equal(target.activationCount, beforeCount);
            assert.equal(activeState.fieldname, scenario.owner);
            assert.equal(messages.length, 1);
            assert.equal(messages[0].title, "التعديل ما زال مفتوحًا");
            messages.length = 0;
        }
    }

    // Regression from the real recording: even if host/DOM state has already drifted
    // to another tab, navigation authority remains the edit-session owner. A lifecycle
    // reconciliation returns the UI to that owner instead of accepting the drift as
    // the new "current" authorization state.
    editingKind = "order";
    activeState.fieldname = "cost_tab";
    const order = frm.layout.tabs.find((tab) => tab.df.fieldname === "order_tab");
    const beforeOrderActivation = order.activationCount;
    formHandlers.on_tab_change(frm);
    assert.equal(activeState.fieldname, "order_tab", "drifted UI must recover to the Order edit owner");
    assert.equal(order.activationCount, beforeOrderActivation + 1);
    assert.equal(order.disabled, false);
    assert.equal(frm.layout.tabs.find((tab) => tab.df.fieldname === "cost_tab").disabled, true);

    // Save/Cancel closes the aggregate session and navigation unlocks immediately.
    editingKind = null;
    formHandlers.almdina_edit_session_changed(frm);
    frm.layout.tabs.forEach((tab) => {
        assert.equal(tab.disabled, false);
        assert.equal(tab.ariaDisabled, undefined);
        assert.equal(tab.tabIndex, undefined);
        assert.equal(tab.title, undefined);
        assert.equal(tab.lockedClass, false);
    });
    const cost = frm.layout.tabs.find((tab) => tab.df.fieldname === "cost_tab");
    assert.equal(cost.set_active(), "activated:cost_tab");
    assert.equal(activeState.fieldname, "cost_tab");
    assert.ok(scheduleCount >= 2, "allowed activations should reconcile the page action projection");

    // Frappe may rebuild Tab instances. Retired instances are restored exactly and
    // the new instances receive the same semantic + native lock contract.
    editingKind = "plan";
    activeState.fieldname = "results_tab";
    const oldTabs = frm.layout.tabs;
    frm.layout.tabs = makeTabs();
    formHandlers.refresh(frm);

    oldTabs.forEach((tab) => {
        assert.equal(tab.set_active, tab.nativeSetActive, "retired Tab instances must regain native methods");
        assert.equal(tab.dataToggle, "tab", "retired markup must regain Bootstrap's original attribute");
        assert.equal(tab.disabled, false, "retired markup must not keep an edit lock");
    });
    frm.layout.tabs.forEach((tab) => {
        assert.notEqual(tab.set_active, tab.nativeSetActive, "rebuilt tabs must be guarded");
        assert.equal(tab.dataToggle, undefined);
        assert.equal(tab.disabled, tab.df.fieldname !== "results_tab");
    });

    const cleanup = cleanups.get("tab-edit-lifecycle-guard");
    assert.equal(typeof cleanup, "function");
    cleanup();
    frm.layout.tabs.forEach((tab) => {
        assert.equal(tab.set_active, tab.nativeSetActive, "document cleanup must restore native Frappe methods");
        assert.equal(tab.dataToggle, "tab", "document cleanup must restore native tab markup");
        assert.equal(tab.disabled, false, "document cleanup must release native navigation locks");
        assert.equal(tab.lockedClass, false);
    });
}

verifyEditOwnerNavigationLock();
console.log("DCO edit-owner navigation lifecycle guard simulation passed");
