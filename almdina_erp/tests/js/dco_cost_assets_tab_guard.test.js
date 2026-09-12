"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

function source(relativePath) {
    return fs.readFileSync(path.resolve(__dirname, "../../", relativePath), "utf8");
}

function verifyCostAssetContract() {
    const fakeWindow = {
        dispatchEvent() {},
    };
    const context = vm.createContext({
        window: fakeWindow,
        console,
        Promise,
        Object,
        Array,
        Map,
        Set,
        String,
        CustomEvent: class CustomEvent {
            constructor(type, options = {}) {
                this.type = type;
                this.detail = options.detail;
            }
        },
    });

    vm.runInContext(
        source("public/js/door_cutting_order/core/door_cutting_order_workspace_asset_registry.js"),
        context,
        { filename: "door_cutting_order_workspace_asset_registry.js" }
    );

    const registry = fakeWindow.AlmdinaDcoWorkspaceAssetRegistry;
    assert.ok(registry, "workspace asset registry should initialize");
    const assets = Array.from(registry.assetsFor("cost"));
    assert.ok(assets.length >= 7, "Cost workspace should expose its lazy asset bundle");
    assert.ok(
        assets.every(asset => asset.endsWith(".js") && !asset.includes("?")),
        "Cost lazy assets must be plain JavaScript paths; Frappe owns cache versioning"
    );
    assert.ok(
        assets.some(asset => asset.endsWith("door_cutting_order_cost_page_layout_ux.js")),
        "Cost page layout must remain in the lazy bundle without a query suffix"
    );
}

function makeTabRoot() {
    let clickHandler = null;
    let addCount = 0;
    let removeCount = 0;
    return {
        nodeType: 1,
        addEventListener(name, handler, capture) {
            assert.equal(name, "click");
            assert.equal(capture, true);
            clickHandler = handler;
            addCount += 1;
        },
        removeEventListener(name, handler, capture) {
            assert.equal(name, "click");
            assert.equal(capture, true);
            if (clickHandler === handler) clickHandler = null;
            removeCount += 1;
        },
        click(fieldname) {
            assert.ok(clickHandler, "tab navigation guard should be installed");
            const link = {
                getAttribute(name) {
                    assert.equal(name, "data-fieldname");
                    return fieldname;
                },
            };
            const event = {
                target: {
                    closest(selector) {
                        assert.equal(selector, ".nav-link[data-fieldname]");
                        return link;
                    },
                },
                prevented: false,
                stopped: false,
                preventDefault() {
                    this.prevented = true;
                },
                stopImmediatePropagation() {
                    this.stopped = true;
                },
            };
            clickHandler(event);
            return event;
        },
        get addCount() {
            return addCount;
        },
        get removeCount() {
            return removeCount;
        },
    };
}

function verifyTabEditGuard() {
    const formHandlers = {};
    const messages = [];
    const cleanups = new Map();
    let editingKind = "plan";
    let activeFieldname = "results_tab";
    let tabRoot = makeTabRoot();

    const formRoot = {
        nodeType: 1,
        querySelector() {
            return null;
        },
        querySelectorAll() {
            return [];
        },
    };
    const pageRoot = {
        nodeType: 1,
        classList: {
            add() {},
            remove() {},
        },
        querySelectorAll() {
            return [];
        },
    };

    const frm = {
        doctype: "Door Cutting Order",
        doc: { doctype: "Door Cutting Order", name: "DCO-GUARD-1" },
        wrapper: formRoot,
        page: { wrapper: pageRoot },
        layout: { tab_link_container: [tabRoot] },
        fields_dict: {},
        is_new() {
            // Keeps this simulation focused on navigation ownership; the guard itself
            // is independent from document persistence state.
            return true;
        },
        get_active_tab() {
            return { df: { fieldname: activeFieldname } };
        },
    };

    const fakeWindow = {
        cur_frm: frm,
        AlmdinaPermissions: {
            version() {
                return 1;
            },
        },
        AlmdinaOrderRevisionUX: {
            captureEditSessionPresence() {
                return editingKind === "order";
            },
            canOfferEditSession() {
                return true;
            },
        },
        AlmdinaPlanEditSessionUX: {
            isEditing() {
                return editingKind === "plan";
            },
            canEditPlanSettings() {
                return true;
            },
        },
        AlmdinaCostEditSessionUX: {
            isEditing() {
                return editingKind === "cost";
            },
            canEditCostWorkspace() {
                return true;
            },
        },
        AlmdinaDocumentContext: {
            scheduleFrame(_frm, _key, callback) {
                callback();
                return 1;
            },
            registerCleanup(_frm, key, cleanup) {
                const previous = cleanups.get(key);
                if (previous) previous();
                cleanups.set(key, cleanup);
                return true;
            },
        },
        addEventListener() {},
        requestAnimationFrame(callback) {
            callback();
            return 1;
        },
    };

    const fakeFrappe = {
        utils: {
            escape_html(value) {
                return String(value || "");
            },
        },
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
        document: {
            getElementById() {
                return {};
            },
            createElement() {
                throw new Error("toolbar creation is outside this guard simulation");
            },
        },
        frappe: fakeFrappe,
        $(selector) {
            if (selector === "head") return { append() {} };
            return { append() {} };
        },
        console,
        Promise,
        Object,
        Array,
        Map,
        Set,
        String,
        Number,
        Boolean,
        __: value => String(value),
    });

    vm.runInContext(
        source("public/js/door_cutting_order/core/door_cutting_order_page_edit_action_ux.js"),
        context,
        { filename: "door_cutting_order_page_edit_action_ux.js" }
    );

    assert.equal(typeof formHandlers.refresh, "function");
    formHandlers.refresh(frm);
    assert.equal(
        tabRoot.addCount,
        1,
        "guard must bind to Frappe's canonical tab-link container"
    );

    for (const scenario of [
        { kind: "plan", current: "results_tab", target: "order_tab" },
        { kind: "cost", current: "cost_tab", target: "results_tab" },
        { kind: "order", current: "order_tab", target: "cost_tab" },
    ]) {
        editingKind = scenario.kind;
        activeFieldname = scenario.current;
        messages.length = 0;
        const blocked = tabRoot.click(scenario.target);
        assert.equal(blocked.prevented, true, `${scenario.kind} edit must block tab navigation`);
        assert.equal(blocked.stopped, true, `${scenario.kind} edit must stop Frappe's tab handler`);
        assert.equal(messages.length, 1);
        assert.equal(messages[0].title, "التعديل ما زال مفتوحًا");
        assert.match(messages[0].message, /احفظ أو ألغِ/);
    }

    editingKind = "plan";
    activeFieldname = "results_tab";
    messages.length = 0;
    const currentTabClick = tabRoot.click("results_tab");
    assert.equal(currentTabClick.prevented, false, "clicking the active tab remains allowed");
    assert.equal(messages.length, 0);

    editingKind = null;
    const allowed = tabRoot.click("cost_tab");
    assert.equal(allowed.prevented, false, "navigation resumes after Save/Cancel closes editing");

    editingKind = "plan";
    activeFieldname = "results_tab";
    messages.length = 0;
    const oldRoot = tabRoot;
    tabRoot = makeTabRoot();
    frm.layout.tab_link_container = [tabRoot];
    formHandlers.refresh(frm);
    assert.ok(oldRoot.removeCount >= 1, "a rebuilt tab strip must release the old guard listener");
    assert.equal(tabRoot.addCount, 1, "a rebuilt tab strip must receive exactly one guard listener");
    const rebuiltBlocked = tabRoot.click("order_tab");
    assert.equal(rebuiltBlocked.prevented, true);
    assert.equal(messages.length, 1);
}

verifyCostAssetContract();
verifyTabEditGuard();
console.log("DCO Cost asset and tab edit guard simulation passed");
