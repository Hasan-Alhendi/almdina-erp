"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

function publicSource(relativePath) {
    return fs.readFileSync(path.resolve(__dirname, "../../public/js", relativePath), "utf8");
}

function pageSource(relativePath) {
    return fs.readFileSync(path.resolve(__dirname, "../../almdina_erp/page", relativePath), "utf8");
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

function queue() {
    const requests = [];
    return {
        requests,
        call() {
            const pending = deferred();
            requests.push(pending);
            return pending.promise;
        },
    };
}

async function flush() {
    await Promise.resolve();
    await new Promise(resolve => setImmediate(resolve));
}

function latestRequestGate() {
    let generation = 0;
    return {
        begin(meta = null) {
            generation += 1;
            return Object.freeze({ generation, meta });
        },
        isCurrent(token) {
            return Boolean(token && token.generation === generation);
        },
        invalidate() {
            generation += 1;
            return generation;
        },
    };
}

function lifecycleScope() {
    let disposed = false;
    const cleanups = new Map();
    return {
        track(cleanup, key) {
            if (cleanups.has(key)) cleanups.get(key)();
            cleanups.set(key, cleanup);
        },
        dispose() {
            if (disposed) return false;
            disposed = true;
            for (const cleanup of cleanups.values()) cleanup();
            cleanups.clear();
            return true;
        },
        isDisposed: () => disposed,
    };
}

function dialogOwner() {
    const owned = new Set();
    return {
        track(dialog) { if (dialog && typeof dialog.hide === "function") owned.add(dialog); return dialog; },
        closeAll() { owned.forEach(dialog => dialog.hide()); owned.clear(); },
    };
}

function eventHarness({ active = true } = {}) {
    const events = new Map();
    const wrapper = { page: {} };
    const other = {};
    const frappe = { container: { page: active ? wrapper : other } };

    function jquery(target) {
        assert.equal(target, wrapper);
        return {
            on(name, callback) {
                events.set(String(name), callback);
                return this;
            },
            off(name = "") {
                const value = String(name);
                if (value.startsWith(".")) {
                    for (const key of [...events.keys()]) {
                        if (key.endsWith(value)) events.delete(key);
                    }
                } else if (value) {
                    events.delete(value);
                } else {
                    events.clear();
                }
                return this;
            },
        };
    }

    function trigger(name) {
        for (const [registered, callback] of [...events.entries()]) {
            if (registered.split(".")[0] === name) callback.call(wrapper);
        }
    }

    return {
        events,
        frappe,
        jquery,
        other,
        wrapper,
        hide() {
            frappe.container.page = other;
            trigger("hide");
        },
        show() {
            frappe.container.page = wrapper;
            wrapper._route = "active-route";
            trigger("show");
        },
    };
}

function loadPageLifecycle(harness, extra = {}) {
    const fakeWindow = {
        frappe: harness.frappe,
        jQuery: harness.jquery,
        ...extra,
    };
    const context = vm.createContext({
        window: fakeWindow,
        frappe: harness.frappe,
        $: harness.jquery,
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
        Error,
        __: value => value,
        ...(extra.context || {}),
    });
    vm.runInContext(publicSource("page_revisit_refresh.js"), context, {
        filename: "page_revisit_refresh.js",
    });
    return { context, fakeWindow };
}

async function testShopFloorActivation() {
    const harness = eventHarness({ active: true });
    harness.wrapper.page = { clear_primary_action() {}, clear_inner_toolbar() {} };
    const loaded = loadPageLifecycle(harness);
    const contextQueue = queue();
    const inboxQueue = queue();
    const archiveQueue = queue();
    let renders = 0;

    loaded.fakeWindow.AlmdinaFrontend = {
        createLatestRequestGate: latestRequestGate,
        createLifecycleScope: lifecycleScope,
        errorMessage(error, fallback) { return error && error.message ? error.message : fallback; },
    };
    loaded.fakeWindow.AlmdinaShopFloorInboxApi = {
        getSessionContext: () => contextQueue.call(),
        getInbox: () => inboxQueue.call(),
        getArchive: () => archiveQueue.call(),
    };
    loaded.fakeWindow.AlmdinaShopFloorInboxViewModel = {
        board: snapshot => ({ routeFilter: snapshot.routeFilter }),
        list: () => ({}),
        account: () => ({}),
    };
    loaded.fakeWindow.AlmdinaShopFloorInboxRenderer = {
        createShell: () => ({}),
        syncTabs() {},
        loading() {},
        renderBoard() { renders += 1; },
        renderList() { renders += 1; },
        renderAccount() { renders += 1; },
        error() {},
        focusSearch() {},
    };
    loaded.fakeWindow.AlmdinaShopFloorInboxInteractions = { bind() {} };
    loaded.fakeWindow.AlmdinaShopFloorInboxDialogs = {
        success() {}, error() {}, confirmTerminal() {}, noWorkers() {}, promptWorker() {}, confirmLogout() {},
    };

    vm.runInContext(publicSource("shop_floor_inbox/state.js"), loaded.context);
    vm.runInContext(publicSource("shop_floor_inbox/controller.js"), loaded.context);
    loaded.fakeWindow.AlmdinaShopFloorInboxController.mount(harness.wrapper);
    assert.equal(contextQueue.requests.length, 1);

    harness.hide();
    contextQueue.requests[0].resolve({ marker: "stale-context" });
    await flush();
    assert.equal(inboxQueue.requests.length, 0, "hidden Shop Floor context must not start list reads");

    harness.show();
    assert.equal(contextQueue.requests.length, 2);
    contextQueue.requests[1].resolve({ marker: "visit-two" });
    await flush();
    assert.equal(inboxQueue.requests.length, 1);
    assert.equal(archiveQueue.requests.length, 1);

    harness.hide();
    inboxQueue.requests[0].resolve([{ name: "OLD" }]);
    archiveQueue.requests[0].resolve([]);
    await flush();
    assert.equal(renders, 0, "Shop Floor list responses after hide must not render");

    harness.show();
    contextQueue.requests[2].resolve({ marker: "visit-three" });
    await flush();
    inboxQueue.requests[1].resolve([{ name: "FRESH" }]);
    archiveQueue.requests[1].resolve([]);
    await flush();
    assert.equal(renders, 1, "one active revisit must render one fresh Shop Floor snapshot");
    assert.equal(harness.events.size, 2, "Shop Floor owns one show/hide listener pair");
}

async function testMasterDataDirtyRevisit() {
    const harness = eventHarness({ active: false });
    const main = {
        htmlCalls: 0,
        html() { this.htmlCalls += 1; return this; },
        off() { return this; },
        on() { return this; },
        find() {
            return {
                get() { return null; },
                prop() { return this; },
                text() { return this; },
                addClass() { return this; },
                removeClass() { return this; },
                length: 0,
            };
        },
    };
    const innerButtons = [];
    harness.wrapper.page = {
        add_inner_button(label, callback) { innerButtons.push({ label, callback }); },
    };

    function jquery(target) {
        if (target === harness.wrapper) {
            const eventsApi = harness.jquery(target);
            eventsApi.find = () => main;
            return eventsApi;
        }
        return main;
    }
    const calls = queue();
    const frappe = harness.frappe;
    frappe.pages = { "factory-master-data": {} };
    frappe.ui = {
        make_app_page() { return harness.wrapper.page; },
    };
    frappe.call = () => calls.call();
    frappe.require = () => Promise.resolve();
    frappe.utils = { escape_html: value => String(value || "") };
    frappe.show_alert = () => {};
    frappe.confirm = (_message, yes) => yes && yes();
    const fakeDocument = { getElementById() { return null; } };
    const fakeWindow = {
        frappe,
        jQuery: jquery,
        document: fakeDocument,
        AlmdinaFrontend: {
            ensureStylesheet: () => Promise.resolve({}),
            createDialogOwner: dialogOwner,
            errorMessage(error, fallback) { return error && error.message ? error.message : fallback; },
        },
    };
    const context = vm.createContext({
        window: fakeWindow,
        document: fakeDocument,
        frappe,
        $: jquery,
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
        Error,
        __: value => value,
    });
    vm.runInContext(publicSource("page_revisit_refresh.js"), context);
    vm.runInContext(pageSource("factory_master_data/factory_master_data.js"), context);
    frappe.pages["factory-master-data"].on_page_load(harness.wrapper);
    assert.equal(calls.requests.length, 0, "Master Data must wait for first activation");

    harness.show();
    await flush();
    assert.equal(calls.requests.length, 1);
    const workflow = harness.wrapper.__almdinaRoutingWorkflowPage;
    harness.hide();
    calls.requests[0].resolve({ message: { routings: [{ name: "OLD" }] } });
    await flush();
    assert.equal(workflow.state.data, null, "Master Data response after hide must be discarded");

    harness.show();
    await flush();
    calls.requests[1].resolve({
        message: { permissions: {}, summary: {}, routings: [], audit: [], operational_roles: [], stage_catalog: [] },
    });
    await flush();
    assert.ok(workflow.state.data);

    workflow.state.editor = { dirty: true };
    harness.hide();
    harness.show();
    await flush();
    assert.equal(calls.requests.length, 2, "dirty routing editor must survive revisit without reload");

    workflow.state.editor.dirty = false;
    harness.hide();
    harness.show();
    await flush();
    assert.equal(calls.requests.length, 3, "clean routing page must refresh once on revisit");
}

async function testDoorDrawingLateBootstrap() {
    const harness = eventHarness({ active: false });
    const moduleLoad = deferred();
    let currentRoute = ["door-drawing", "DCO-1", "ROW-1"];
    const main = {
        innerHTML: "",
        querySelector() { return null; },
    };
    harness.wrapper.querySelector = selector => selector === ".layout-main-section" ? main : null;
    const bodyClasses = new Set();
    const fakeDocument = {
        body: {
            classList: {
                add(value) { bodyClasses.add(value); },
                remove(value) { bodyClasses.delete(value); },
            },
        },
    };
    const frappe = harness.frappe;
    frappe.pages = { "door-drawing": {} };
    frappe.ui = { make_app_page() {} };
    frappe.require = () => moduleLoad.promise;
    frappe.get_route = () => currentRoute;
    const loaded = loadPageLifecycle(harness, {
        document: fakeDocument,
        AlmdinaFrontend: { ensureStylesheet: () => Promise.resolve({}) },
        context: { document: fakeDocument },
    });
    loaded.context.document = fakeDocument;
    loaded.fakeWindow.AlmdinaSpecialShapeDocumentation = {
        WorkspaceController: {
            mount() {
                return {
                    open(routeContext) {
                        loaded.fakeWindow.openCalls = (loaded.fakeWindow.openCalls || 0) + 1;
                        loaded.fakeWindow.openedContexts = [
                            ...(loaded.fakeWindow.openedContexts || []),
                            routeContext,
                        ];
                    },
                    suspend() { loaded.fakeWindow.suspendCalls = (loaded.fakeWindow.suspendCalls || 0) + 1; },
                    showRouteError() {},
                };
            },
        },
    };
    Object.assign(loaded.context.frappe, frappe);
    vm.runInContext(pageSource("door_drawing/door_drawing.js"), loaded.context);
    frappe.pages["door-drawing"].on_page_load(harness.wrapper);

    frappe.container.page = harness.wrapper;
    const firstShow = frappe.pages["door-drawing"].on_page_show(harness.wrapper);
    harness.hide();
    moduleLoad.resolve();
    await firstShow;
    assert.equal(loaded.fakeWindow.openCalls || 0, 0, "late drawing bootstrap must not open after hide");

    frappe.container.page = harness.wrapper;
    await frappe.pages["door-drawing"].on_page_show(harness.wrapper);
    assert.equal(loaded.fakeWindow.openCalls, 1, "the next active drawing visit must open its route once");

    currentRoute = ["door-drawing", "DCO-2", "ROW-A"];
    const supersededShow = frappe.pages["door-drawing"].on_page_show(harness.wrapper);
    currentRoute = ["door-drawing", "DCO-2", "ROW-B"];
    const latestShow = frappe.pages["door-drawing"].on_page_show(harness.wrapper);
    await Promise.all([supersededShow, latestShow]);
    assert.equal(loaded.fakeWindow.openCalls, 2, "duplicate show must open only the latest route context");
    assert.equal(loaded.fakeWindow.openedContexts.at(-1).pieceName, "ROW-B");
    assert.equal(harness.events.size, 2, "Door Drawing remount contract owns one listener pair");
}

async function testDoorCuttingOrderListActiveGuard() {
    const harness = eventHarness({ active: true });
    const frames = new Map();
    let nextFrame = 0;
    const result = {
        querySelectorAll() { return []; },
        appendChild() {},
    };
    const classes = new Set();
    const root = harness.wrapper;
    root.nodeType = 1;
    root.classList = {
        add(value) { classes.add(value); },
        toggle(value, enabled) { if (enabled) classes.add(value); else classes.delete(value); },
        contains(value) { return classes.has(value); },
    };
    root.querySelector = selector => selector === ".result" ? result : null;
    root.querySelectorAll = () => [];
    const calls = queue();
    const frappe = harness.frappe;
    frappe.listview_settings = {};
    frappe.call = () => calls.call();
    frappe.utils = { escape_html: value => String(value || "") };
    frappe.datetime = {};
    const fakeWindow = {
        frappe,
        jQuery: harness.jquery,
        AlmdinaResponsiveDevice: { usesCardLayout: () => false },
        addEventListener() {},
        requestAnimationFrame(callback) {
            nextFrame += 1;
            frames.set(nextFrame, callback);
            return nextFrame;
        },
        cancelAnimationFrame(id) { frames.delete(id); },
        clearTimeout(id) { frames.delete(id); },
    };
    const runFrames = () => {
        const pending = [...frames.values()];
        frames.clear();
        pending.forEach(callback => callback());
    };
    const context = vm.createContext({
        window: fakeWindow,
        frappe,
        $: harness.jquery,
        document: { getElementById() { return {}; }, head: { appendChild() {} }, createElement() { return {}; } },
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
        Error,
        requestAnimationFrame: callback => fakeWindow.requestAnimationFrame(callback),
        __: value => value,
    });
    vm.runInContext(publicSource("page_revisit_refresh.js"), context);
    vm.runInContext(publicSource("door_cutting_order/list_view/door_cutting_order_list.js"), context);

    const doc = { name: "DCO-1", status: "Draft" };
    const listview = {
        doctype: "Door Cutting Order",
        page: { wrapper: root, fields_dict: {} },
        data: [doc],
        get_args() { return { filters: [] }; },
    };
    const settings = frappe.listview_settings["Door Cutting Order"];
    settings.onload(listview);
    runFrames();
    settings.refresh(listview);
    runFrames();
    assert.equal(calls.requests.length, 1);

    harness.hide();
    calls.requests[0].resolve({ message: { personal_view: true, orders: { "DCO-1": { can_start_stage: true } } } });
    await flush();
    assert.equal(doc.__almdinaProductionActionContext, null, "hidden list response must not decorate rows");

    harness.show();
    runFrames();
    assert.equal(calls.requests.length, 2);
    calls.requests[1].resolve({ message: { personal_view: true, orders: { "DCO-1": { can_start_stage: true } } } });
    await flush();
    assert.equal(doc.__almdinaProductionActionContext.canStart, true);
}

async function testReplacementPieceCurrentFormGuard() {
    const handlers = {};
    const calls = queue();
    const fakeWindow = {
        cur_frm: null,
        AlmdinaPermissions: { can: () => false },
        AlmdinaFrontend: { createDialogOwner: dialogOwner },
    };
    const frappe = {
        ui: { form: { on(_doctype, events) { Object.assign(handlers, events); } } },
        call: () => calls.call(),
        show_alert() {},
        confirm(_message, yes) { if (yes) yes(); },
        prompt() {},
        router: { on() {} },
        utils: { escape_html: value => String(value || "") },
    };
    const context = vm.createContext({
        window: fakeWindow,
        frappe,
        console,
        Promise,
        Object,
        Array,
        String,
        Number,
        Boolean,
        JSON,
        Error,
        __: value => value,
    });
    vm.runInContext(publicSource("replacement_piece.js"), context);
    const form = {
        doc: { name: "REP-1" },
        is_new: () => false,
        remove_custom_button() {},
        add_custom_button() {},
    };
    fakeWindow.cur_frm = form;
    handlers.refresh(form);
    fakeWindow.cur_frm = { doc: { name: "OTHER" } };
    calls.requests[0].resolve({ message: { replacement_name: "REP-1", actions: {} } });
    await flush();
    assert.equal(form.__almdinaReplacementContext, undefined, "hidden Replacement form must reject late context");

    fakeWindow.cur_frm = form;
    handlers.refresh(form);
    calls.requests[1].resolve({ message: { replacement_name: "REP-1", actions: {} } });
    await flush();
    assert.equal(form.__almdinaReplacementContext.replacement_name, "REP-1");
}

function verifyAllPageEntriesUseActivationOwnership() {
    const pages = [
        "factory_approval_queue/factory_approval_queue.js",
        "factory_master_data/factory_master_data.js",
        "factory_performance_benchmark/factory_performance_benchmark.js",
        "factory_plan_archive/factory_plan_archive.js",
        "factory_stock_settings/factory_stock_settings.js",
        "factory_system_preflight/factory_system_preflight.js",
        "shop_floor_inbox/shop_floor_inbox.js",
        "door_drawing/door_drawing.js",
    ];
    pages.forEach(filename => {
        const source = pageSource(filename);
        assert.match(source, /bindActivationLifecycle/, filename);
        assert.doesNotMatch(source, /refreshOnRevisit/, filename);
    });
}

(async () => {
    verifyAllPageEntriesUseActivationOwnership();
    await testShopFloorActivation();
    await testMasterDataDirtyRevisit();
    await testDoorDrawingLateBootstrap();
    await testDoorCuttingOrderListActiveGuard();
    await testReplacementPieceCurrentFormGuard();
    console.log("Project-wide frontend lifecycle simulations passed");
})().catch(error => {
    console.error(error);
    process.exitCode = 1;
});
