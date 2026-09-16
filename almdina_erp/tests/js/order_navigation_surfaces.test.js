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

function costWrapper() {
    return {
        content: "",
        shell: false,
        empty() {
            this.content = "";
            this.shell = false;
            return this;
        },
        find(selector) {
            return { length: selector === ".dco-cost-shell" && this.shell ? 1 : 0 };
        },
    };
}

async function verifyCostSnapshotIsolation() {
    const handlers = {};
    const calls = [];
    const renders = [];
    const wrapper = costWrapper();

    const fakeWindow = {
        cur_frm: null,
        clearTimeout() {},
        AlmdinaPermissions: {
            canDocument(_frm, capability) {
                return capability === "view_costs";
            },
            can(capability) {
                return capability === "view_costs";
            },
        },
        AlmdinaOrderTabPermissionsUX: { apply() {} },
        AlmdinaOrderCostUX: {
            render(frm) {
                wrapper.shell = true;
                renders.push(frm.doc.total_cost_usd);
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
    };
    const context = vm.createContext({
        window: fakeWindow,
        frappe: fakeFrappe,
        console,
        Promise,
        Object,
        Set,
        Map,
        String,
        Number,
        Boolean,
        Array,
        MutationObserver: class {
            observe() {}
            disconnect() {}
        },
        setTimeout() {
            return 1;
        },
        __: value => value,
    });
    vm.runInContext(source("door_cutting_order/core/door_cutting_order_document_context.js"), context);
    vm.runInContext(source("door_cutting_order/costing/door_cutting_order_cost_permissions_ux.js"), context);

    const makeDoc = (name, total) => ({
        doctype: "Door Cutting Order",
        name,
        status: "Draft",
        docstatus: 0,
        total_cost_usd: total,
        pieces: [],
    });
    const frm = {
        doctype: "Door Cutting Order",
        doc: makeDoc("DCO-A", 10),
        fields_dict: { order_cost_invoice_html: { $wrapper: wrapper } },
        is_new() {
            return false;
        },
        set_df_property() {},
    };
    fakeWindow.cur_frm = frm;
    fakeWindow.AlmdinaDocumentContext.synchronize(frm);

    fakeWindow.AlmdinaCostPermissionsUX.apply(frm);
    assert.equal(
        calls.length,
        0,
        "CostPermissions must never start its own financial snapshot request"
    );
    assert.deepEqual(renders, [10]);

    frm.doc = makeDoc("DCO-B", 20);
    fakeWindow.AlmdinaDocumentContext.synchronize(frm);
    frm.doc = makeDoc("DCO-A", 42);
    fakeWindow.AlmdinaDocumentContext.synchronize(frm);

    fakeWindow.AlmdinaCostPermissionsUX.apply(frm);
    assert.equal(calls.length, 0);
    assert.equal(frm.doc.total_cost_usd, 42);
    assert.deepEqual(
        renders,
        [10, 42],
        "the permission surface must render only the current document projection"
    );

    frm.doc = makeDoc("DCO-B", 30);
    fakeWindow.AlmdinaDocumentContext.synchronize(frm);
    fakeWindow.AlmdinaCostPermissionsUX.apply(frm);
    assert.equal(calls.length, 0);
    assert.equal(frm.doc.total_cost_usd, 30);
    assert.deepEqual(renders, [10, 42, 30]);
}

async function verifyProductionActionsRecoverAfterPermissions() {
    const handlers = {};
    const listeners = {};
    const timers = [];
    const calls = [];
    const capabilities = new Set();
    let permissionRefreshCalls = 0;
    let generation = 1;

    const fakeWindow = {
        cur_frm: null,
        AlmdinaPermissions: {
            canDocument(_frm, capability) {
                return capabilities.has(capability);
            },
            can(capability) {
                return capabilities.has(capability);
            },
            profile() {
                return "full";
            },
            refresh() {
                permissionRefreshCalls += 1;
                return jqueryThenable(Promise.resolve({ version: 2 }));
            },
        },
        AlmdinaDocumentContext: {
            capture(frm) {
                return Object.freeze({
                    identity: `${frm.doctype}::${frm.doc.name}`,
                    generation,
                });
            },
            isCurrent(frm, token) {
                return Boolean(
                    fakeWindow.cur_frm === frm
                    && token.identity === `${frm.doctype}::${frm.doc.name}`
                    && token.generation === generation
                );
            },
        },
        addEventListener(event, callback) {
            listeners[event] = callback;
        },
        setTimeout(callback) {
            timers.push(callback);
            return timers.length;
        },
    };
    const fakeFrappe = {
        almdina: {},
        session: { user: "worker@example.com" },
        utils: { escape_html: value => String(value) },
        ui: {
            form: {
                on(doctype, events) {
                    assert.equal(doctype, "Door Cutting Order");
                    Object.assign(handlers, events);
                },
            },
        },
        provide() {},
        call(options) {
            const pending = deferred();
            calls.push({ options, pending });
            return jqueryThenable(pending.promise);
        },
        set_route() {},
    };
    const context = vm.createContext({
        window: fakeWindow,
        frappe: fakeFrappe,
        console,
        Promise,
        Object,
        Set,
        Map,
        String,
        Number,
        Boolean,
        Array,
        __: value => value,
    });
    vm.runInContext(source("door_cutting_order/production/shop_floor_order_ux.js"), context);

    const added = [];
    const frm = {
        doctype: "Door Cutting Order",
        doc: {
            doctype: "Door Cutting Order",
            name: "DCO-A",
            status: "Draft",
            production_path: "",
            current_production_stage: "",
        },
        fields_dict: {},
        meta: { fields: [] },
        page: {
            wrapper: {
                nodeType: 1,
                querySelectorAll() {
                    return added.map(button => ({ textContent: button.label }));
                },
            },
        },
        is_new() {
            return false;
        },
        add_custom_button(label, _handler, group) {
            added.push({ label, group });
            this.custom_buttons = this.custom_buttons || {};
            this.custom_buttons[label] = { group };
        },
        remove_custom_button(label, group) {
            for (let index = added.length - 1; index >= 0; index -= 1) {
                if (added[index].label === label && (!group || added[index].group === group)) {
                    added.splice(index, 1);
                }
            }
            if (this.custom_buttons) delete this.custom_buttons[label];
        },
        set_df_property() {},
        enable_save() {},
    };
    fakeWindow.cur_frm = frm;

    handlers.refresh(frm);
    assert.equal(added.some(button => button.group === "صالة الإنتاج"), false);

    await flushPromises();
    assert.equal(
        permissionRefreshCalls,
        0,
        "production action recovery must not start a second permission request"
    );
    capabilities.add("dispatch_order");
    assert.equal(typeof listeners["almdina:permissions-updated"], "function");
    listeners["almdina:permissions-updated"]();
    await flushPromises();
    assert.equal(
        added.some(button => button.label === "إرسال للإنتاج" && !button.group),
        true,
        "production actions must be rebuilt when the jqXHR-like permission refresh completes"
    );
    assert.equal(fakeWindow.AlmdinaShopFloorOrderUX.productionActionsReady(frm), true);

    // Frappe can rebuild the toolbar while revisiting the same order.  The
    // document/status key remains unchanged, so readiness must also verify that
    // the expected DOM/custom-button surface still exists.
    added.length = 0;
    assert.ok(frm.custom_buttons["إرسال للإنتاج"], "the stale Frappe button cache remains");
    assert.equal(fakeWindow.AlmdinaShopFloorOrderUX.productionActionsReady(frm), false);
    fakeWindow.AlmdinaShopFloorOrderUX.reconcileProductionActions(frm);
    assert.equal(fakeWindow.AlmdinaShopFloorOrderUX.productionActionsReady(frm), true);

    capabilities.clear();
    capabilities.add("start_assigned_stage");
    frm.doc = {
        doctype: "Door Cutting Order",
        name: "DCO-A",
        status: "At Drawing",
        production_path: "Drawing",
        current_production_stage: "STAGE-1",
    };
    fakeWindow.AlmdinaShopFloorOrderUX.reconcileProductionActions(frm);
    assert.equal(calls.length, 1);

    generation += 1;
    frm.doc = { ...frm.doc, name: "DCO-B" };
    generation += 1;
    frm.doc = { ...frm.doc, name: "DCO-A" };
    frm.__almdinaProductionActionsPromise = null;
    frm.__almdinaProductionActionsContext = null;
    calls[0].pending.resolve({
        message: {
            active_stage_status: "Pending",
            active_stage_assigned_to: "worker@example.com",
            can_start_stage: true,
            route_stages: [{ stage_type: "Drawing", department: "رسم" }],
        },
    });
    await flushPromises();
    assert.equal(
        added.some(button => button.label === "بدء العمل"),
        false,
        "a stage response from the first A visit must not add actions to the later A visit"
    );
}

async function verifyDispatchWithoutHistoryReturnsToOrderList() {
    const handlers = {};
    const calls = [];
    const routes = [];
    const reloads = [];
    const capabilities = new Set(["dispatch_order"]);
    let dialog = null;

    class FakeDialog {
        constructor(config) {
            this.config = config;
            this.fields_dict = {
                route_preview: { $wrapper: { html() {} } },
            };
            dialog = this;
        }

        show() {}

        hide() {}

        get_value() {
            return "";
        }

        set_value() {}

        set_df_property() {}
    }

    const fakeWindow = {
        cur_frm: null,
        AlmdinaPermissions: {
            canDocument(_frm, capability) {
                return capabilities.has(capability);
            },
            can(capability) {
                return capabilities.has(capability);
            },
            profile() {
                return "shop_floor";
            },
        },
        AlmdinaDocumentContext: {
            capture(frm) {
                return `${frm.doctype}::${frm.doc.name}`;
            },
            isCurrent() {
                return true;
            },
        },
        addEventListener() {},
        setTimeout() {
            return 1;
        },
    };
    const fakeFrappe = {
        almdina: {},
        session: { user: "worker@example.com" },
        utils: { escape_html: value => String(value) },
        ui: {
            Dialog: FakeDialog,
            form: {
                on(doctype, events) {
                    Object.assign(handlers, events);
                },
            },
        },
        provide() {},
        show_alert() {},
        msgprint() {},
        call(options) {
            const pending = deferred();
            calls.push({ options, pending });
            return jqueryThenable(pending.promise);
        },
        set_route(...parts) {
            routes.push(parts);
            return Promise.resolve(parts);
        },
    };
    const context = vm.createContext({
        window: fakeWindow,
        frappe: fakeFrappe,
        console,
        Promise,
        Object,
        Set,
        Map,
        String,
        Number,
        Boolean,
        Array,
        __: value => value,
    });
    vm.runInContext(source("door_cutting_order/production/shop_floor_order_ux.js"), context);

    const frm = {
        doctype: "Door Cutting Order",
        doc: {
            doctype: "Door Cutting Order",
            name: "DCO-A",
            status: "Draft",
            production_path: "",
            current_production_stage: "",
        },
        fields_dict: {},
        meta: { fields: [] },
        page: { wrapper: { nodeType: 1, querySelectorAll() { return []; } } },
        is_new() {
            return false;
        },
        add_custom_button() {},
        remove_custom_button() {},
        set_df_property() {},
        enable_save() {},
        reload_doc() {
            reloads.push("DCO-A");
            return Promise.resolve();
        },
    };
    fakeWindow.cur_frm = frm;

    fakeFrappe.almdina.open_dispatch_dialog(frm);
    assert.equal(calls.length, 1);
    assert.equal(
        calls[0].options.method,
        "almdina_erp.almdina_erp.services.shop_floor_service.get_dispatch_options"
    );
    calls[0].pending.resolve({
        message: {
            default_path: "Drawing",
            paths: [{
                value: "Drawing",
                label: "Drawing",
                stages: [{ department: "رسم", stage_type: "Drawing", operational_role: "عامل رسم" }],
            }],
            workers: {
                Drawing: [{ name: "cnc@example.com", full_name: "عامل" }],
            },
        },
    });
    await flushPromises();
    assert.equal(Boolean(dialog), true);
    dialog.config.primary_action({ path: "Drawing", assignee: "cnc@example.com" });
    await flushPromises();
    assert.equal(
        calls[1].options.method,
        "almdina_erp.almdina_erp.services.shop_floor_service.dispatch_order"
    );
    calls[1].pending.resolve({ message: { name: "DCO-A" } });
    await flushPromises();
    assert.deepEqual(routes, [["List", "Door Cutting Order"]]);
    assert.deepEqual(reloads, []);

    capabilities.add("view_all_orders");
    routes.length = 0;
    fakeFrappe.almdina.open_dispatch_dialog(frm);
    await flushPromises();
    calls[2].pending.resolve({
        message: {
            default_path: "Drawing",
            paths: [{
                value: "Drawing",
                label: "Drawing",
                stages: [{ department: "رسم", stage_type: "Drawing", operational_role: "عامل رسم" }],
            }],
            workers: {
                Drawing: [{ name: "cnc@example.com", full_name: "عامل" }],
            },
        },
    });
    await flushPromises();
    dialog.config.primary_action({ path: "Drawing", assignee: "cnc@example.com" });
    await flushPromises();
    calls[3].pending.resolve({ message: { name: "DCO-A" } });
    await flushPromises();
    assert.deepEqual(routes, []);
    assert.deepEqual(reloads, ["DCO-A"]);
}

(async () => {
    await verifyCostSnapshotIsolation();
    await verifyProductionActionsRecoverAfterPermissions();
    await verifyDispatchWithoutHistoryReturnsToOrderList();
    console.log("Order navigation surface isolation simulation passed");
})().catch(error => {
    console.error(error);
    process.exitCode = 1;
});
