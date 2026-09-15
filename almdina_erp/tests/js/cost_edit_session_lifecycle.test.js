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
    const promise = new Promise((res, rej) => {
        resolve = res;
        reject = rej;
    });
    return { promise, resolve, reject };
}

function baseSnapshot(rate = 10, cutting = 2) {
    return {
        order: {
            board_rate_usd: rate,
            cutting_cost_per_board_usd: cutting,
        },
        pieces: [],
    };
}

function makeField() {
    return {
        df: {},
        refreshCount: 0,
        refresh() { this.refreshCount += 1; },
    };
}

function makeEnvironment(options = {}) {
    const formHandlers = {};
    const events = [];
    const messages = [];
    const alerts = [];
    const mounts = [];
    const unmounts = [];
    const focuses = [];
    let generation = 1;
    let apiLoadCalls = 0;
    let saveCalls = 0;

    const frm = {
        doctype: "Door Cutting Order",
        doc: {
            doctype: "Door Cutting Order",
            name: "DCO-COST-LIFECYCLE-A",
            docstatus: 0,
            revision_state: "Current",
            status: "Draft",
            pieces: [],
        },
        fields_dict: {
            board_rate_usd: makeField(),
            cutting_cost_per_board_usd: makeField(),
        },
        is_new() { return false; },
        is_dirty() { return false; },
        trigger(name) { events.push(name); },
    };

    const fakeWindow = {
        cur_frm: frm,
        dispatchEvent(event) { events.push(event.type); },
        addEventListener() {},
        requestAnimationFrame(callback) { callback(); return 1; },
        AlmdinaDocumentContext: {
            formIdentity(target) {
                return `Door Cutting Order::${target.doc.name}`;
            },
            capture(target) {
                return Object.freeze({
                    identity: `Door Cutting Order::${target.doc.name}`,
                    generation,
                });
            },
            isCurrent(target, token) {
                return fakeWindow.cur_frm === target
                    && token.generation === generation
                    && token.identity === `Door Cutting Order::${target.doc.name}`;
            },
            scheduleFrame(_target, _key, callback) {
                callback();
                return 1;
            },
        },
        AlmdinaPermissions: {
            canDocument(_target, capability) {
                return [
                    "view_costs",
                    "edit_cost_settings",
                    "approve_special_price",
                    "edit_special_price",
                ].includes(capability);
            },
        },
        AlmdinaWorkspaceFieldEditor: {
            mount(_target, fields, draft, onPatch) {
                mounts.push({ fields: [...fields], draft: { ...draft }, onPatch });
            },
            unmount(_target, fields) { unmounts.push([...fields]); },
            focus(_target, fieldname) { focuses.push(fieldname); },
        },
        AlmdinaCostWorkspacePresenterAdapter: {
            project() {},
        },
        AlmdinaCostPermissionsUX: {
            pendingPricePieces() { return []; },
            async flushPendingPriceEdits() { return false; },
            async discardPendingPriceEdits() { return false; },
        },
        AlmdinaCostWorkspaceAPI: {
            load() {
                apiLoadCalls += 1;
                return options.loadImpl ? options.loadImpl() : Promise.resolve(baseSnapshot());
            },
            async saveSettings(orderName, payload) {
                saveCalls += 1;
                assert.equal(orderName, "DCO-COST-LIFECYCLE-A");
                return baseSnapshot(payload.board_rate_usd, payload.cutting_cost_per_board_usd);
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
        msgprint(payload) { messages.push(payload); },
        show_alert(payload) { alerts.push(payload); },
        utils: { escape_html(value) { return String(value || ""); } },
    };

    const context = vm.createContext({
        window: fakeWindow,
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
        structuredClone,
        CustomEvent: class CustomEvent {
            constructor(type, init = {}) {
                this.type = type;
                this.detail = init.detail;
            }
        },
        __: value => String(value),
    });
    context.window.window = context.window;

    vm.runInContext(
        source("public/js/door_cutting_order/core/door_cutting_order_workspace_store.js"),
        context,
        { filename: "door_cutting_order_workspace_store.js" }
    );
    fakeWindow.AlmdinaWorkspaceStore = context.window.AlmdinaWorkspaceStore;

    vm.runInContext(
        source("public/js/door_cutting_order/costing/door_cutting_order_cost_workspace_state.js"),
        context,
        { filename: "door_cutting_order_cost_workspace_state.js" }
    );
    vm.runInContext(
        source("public/js/door_cutting_order/costing/door_cutting_order_cost_edit_session_ux.js"),
        context,
        { filename: "door_cutting_order_cost_edit_session_ux.js" }
    );

    return {
        context,
        window: fakeWindow,
        frm,
        formHandlers,
        events,
        messages,
        alerts,
        mounts,
        unmounts,
        focuses,
        apiLoadCalls: () => apiLoadCalls,
        saveCalls: () => saveCalls,
        bumpGeneration() { generation += 1; },
    };
}

async function verifyHappyPathAndBackgroundReadGuard() {
    const env = makeEnvironment();
    const state = env.window.AlmdinaCostWorkspaceState;
    const edit = env.window.AlmdinaCostEditSessionUX;

    await state.load(env.frm);
    assert.equal(state.snapshot(env.frm).status, "ready");
    assert.equal(env.apiLoadCalls(), 1);

    assert.equal(await edit.startEditing(env.frm), true);
    let current = state.snapshot(env.frm);
    assert.equal(current.editing, true, "startEditing should enter the canonical store session");
    assert.ok(current.draft, "editing must own a draft");
    assert.ok(env.mounts.length >= 1, "detached cost controls should mount only after beginEdit succeeds");
    assert.ok(env.focuses.includes("board_rate_usd"));

    const callsBeforeBackgroundRead = env.apiLoadCalls();
    const preserved = await state.load(env.frm, { force: true });
    assert.equal(preserved.editing, true);
    assert.ok(preserved.draft);
    assert.equal(
        env.apiLoadCalls(),
        callsBeforeBackgroundRead,
        "a forced/background Cost GET must not start while editing"
    );

    assert.equal(await edit.cancelEditing(env.frm), true);
    current = state.snapshot(env.frm);
    assert.equal(current.editing, false);
    assert.equal(current.draft, null);
    assert.equal(current.dirty, false);

    assert.equal(await edit.startEditing(env.frm), true);
    const store = state.storeFor(env.frm);
    assert.equal(store.patchDraft({ board_rate_usd: 12 }), true);
    assert.equal(await edit.saveEditing(env.frm), true);
    current = state.snapshot(env.frm);
    assert.equal(current.editing, false);
    assert.equal(current.data.order.board_rate_usd, 12);
    assert.equal(env.saveCalls(), 1);
    assert.ok(env.alerts.length >= 1);
}

async function verifyBeginEditFailureIsTransactional() {
    const formHandlers = {};
    const messages = [];
    let mounts = 0;
    let signals = 0;
    const store = {
        snapshot() {
            return {
                status: "ready",
                editing: false,
                data: baseSnapshot(),
            };
        },
        beginEdit() { return false; },
    };
    const frm = {
        doctype: "Door Cutting Order",
        doc: {
            doctype: "Door Cutting Order",
            name: "DCO-BEGIN-FAIL",
            docstatus: 0,
            revision_state: "Current",
            status: "Draft",
            pieces: [],
        },
        fields_dict: {
            board_rate_usd: makeField(),
            cutting_cost_per_board_usd: makeField(),
        },
        is_new() { return false; },
        is_dirty() { return false; },
        trigger() { signals += 1; },
    };
    const fakeWindow = {
        cur_frm: frm,
        addEventListener() {},
        requestAnimationFrame(callback) { callback(); },
        AlmdinaDocumentContext: {
            capture() { return { identity: "DCO-BEGIN-FAIL" }; },
            isCurrent(target) { return fakeWindow.cur_frm === target; },
            scheduleFrame(_target, _key, callback) { callback(); },
        },
        AlmdinaPermissions: {
            canDocument() { return true; },
        },
        AlmdinaCostWorkspaceState: {
            storeFor() { return store; },
            settings() { return { board_rate_usd: 10, cutting_cost_per_board_usd: 2 }; },
            snapshot() { return store.snapshot(); },
        },
        AlmdinaWorkspaceFieldEditor: {
            mount() { mounts += 1; },
            unmount() {},
            focus() {},
        },
    };
    const fakeFrappe = {
        ui: { form: { on(_doctype, handlers) { Object.assign(formHandlers, handlers); } } },
        msgprint(payload) { messages.push(payload); },
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
        __: value => String(value),
    });
    vm.runInContext(
        source("public/js/door_cutting_order/costing/door_cutting_order_cost_edit_session_ux.js"),
        context,
        { filename: "door_cutting_order_cost_edit_session_ux.js" }
    );

    const result = await fakeWindow.AlmdinaCostEditSessionUX.startEditing(frm);
    assert.equal(result, false);
    assert.equal(mounts, 0, "failed beginEdit must not mount draft controls");
    assert.equal(signals, 0, "failed beginEdit must not signal a successful edit transition");
    assert.ok(messages.length >= 1);
}

async function verifyStaleStartCannotMutateNextDocument() {
    const gate = deferred();
    const env = makeEnvironment({ loadImpl: () => gate.promise });
    const edit = env.window.AlmdinaCostEditSessionUX;
    const state = env.window.AlmdinaCostWorkspaceState;

    const startPromise = edit.startEditing(env.frm);
    assert.equal(env.apiLoadCalls(), 1);

    env.frm.doc.name = "DCO-COST-LIFECYCLE-B";
    env.bumpGeneration();
    gate.resolve(baseSnapshot());

    assert.equal(await startPromise, false, "stale A load must not start an edit session on B");
    const current = state.snapshot(env.frm);
    assert.equal(current.editing, false);
    assert.equal(env.mounts.length, 0);
}

(async () => {
    await verifyHappyPathAndBackgroundReadGuard();
    await verifyBeginEditFailureIsTransactional();
    await verifyStaleStartCannotMutateNextDocument();
    console.log("Cost edit-session lifecycle simulation passed");
})().catch((error) => {
    console.error(error);
    process.exitCode = 1;
});
