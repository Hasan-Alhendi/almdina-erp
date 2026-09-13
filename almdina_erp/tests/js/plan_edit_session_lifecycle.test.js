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
    const promise = new Promise((res) => { resolve = res; });
    return { promise, resolve };
}

function settings() {
    return {
        packing_mode: "guillotine", cutting_machine_type: "panel_saw", kerf_mm: 3,
        trim_margin_mm: 5, optimization_time_limit_sec: 30,
    };
}

function environment() {
    const events = [];
    const alerts = [];
    const pendingLoad = deferred();
    const pendingSave = deferred();
    let loadMode = "ready";
    let saveMode = "ready";
    let loadCalls = 0;
    let cancelCalls = 0;
    const state = {
        status: "ready",
        data: {
            approved_plan: "PLAN-1",
            optimization_catalog: [{ id: "guillotine", label: "Guillotine" }],
            machine_type_catalog: [{ id: "panel_saw", label: "Panel saw" }],
        },
        editing: false, dirty: false, draft: null,
    };
    const frm = {
        doctype: "Door Cutting Order",
        doc: { doctype: "Door Cutting Order", name: "DCO-PLAN-A", docstatus: 0, revision_state: "Current", status: "Draft" },
        fields_dict: {},
        is_new() { return false; },
        is_dirty() { return false; },
        trigger(name) { events.push(name); },
    };
    const fakeWindow = {
        cur_frm: frm,
        addEventListener() {},
        dispatchEvent(event) { events.push(event.type); },
        AlmdinaDocumentContext: {
            capture(target) { return Object.freeze({ identity: `Door Cutting Order::${target.doc.name}`, generation: 1 }); },
            isCurrent(target, token) {
                return fakeWindow.cur_frm === target
                    && token.identity === `Door Cutting Order::${target.doc.name}`
                    && token.generation === 1;
            },
            scheduleFrame(_target, _key, callback) { callback(); return 1; },
        },
        AlmdinaPermissions: { canDocument(_target, capability) { return capability === "edit_optimizer_settings"; } },
        AlmdinaPlanWorkspacePresenterAdapter: { activeSettings() { return settings(); }, project() {} },
        AlmdinaPlanFieldAccessAdapter: { apply() {} },
        AlmdinaPlanWorkspaceState: {
            storeFor() {
                return {
                    snapshot() { return state; },
                    beginEdit(seed) { state.editing = true; state.draft = { ...seed }; state.dirty = false; },
                    cancelEdit() { cancelCalls += 1; state.editing = false; state.draft = null; state.dirty = false; },
                };
            },
            snapshot() { return state; },
            activePlan() { return { settings: settings() }; },
            load() {
                loadCalls += 1;
                return loadMode === "pending" ? pendingLoad.promise : Promise.resolve(state);
            },
        },
        AlmdinaPlanWorkspaceAPI: {
            saveSettings() { return saveMode === "pending" ? pendingSave.promise : Promise.resolve({}); },
        },
    };
    const frappe = {
        ui: { form: { on() {} } }, msgprint() {},
        show_alert(message) { alerts.push(message); },
        utils: { escape_html(value) { return String(value); } },
    };
    const context = vm.createContext({ window: fakeWindow, frappe, __: value => String(value), console, Object, String, Number, Boolean, Promise, Set, WeakMap });
    fakeWindow.window = fakeWindow;
    vm.runInContext(source("public/js/door_cutting_order/core/door_cutting_order_edit_session_coordinator.js"), context);
    vm.runInContext(source("public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_edit_session_ux.js"), context);
    return {
        frm, window: fakeWindow, state, events, alerts, pendingLoad, pendingSave,
        setLoadMode(value) { loadMode = value; }, setSaveMode(value) { saveMode = value; },
        loadCalls: () => loadCalls, cancelCalls: () => cancelCalls,
    };
}

async function run() {
    const startEnv = environment();
    startEnv.state.status = "idle";
    startEnv.setLoadMode("pending");
    const start = startEnv.window.AlmdinaPlanEditSessionUX.startEditing(startEnv.frm);
    startEnv.window.cur_frm = { doctype: "Door Cutting Order", doc: { name: "DCO-PLAN-B" } };
    startEnv.pendingLoad.resolve(startEnv.state);
    assert.equal(await start, false, "a late Plan load from A must not open an edit session on a recycled surface");
    assert.equal(startEnv.state.editing, false);
    assert.equal(startEnv.events.length, 0, "stale start must not emit edit/session UI effects");

    const saveEnv = environment();
    const edit = saveEnv.window.AlmdinaPlanEditSessionUX;
    assert.equal(await edit.startEditing(saveEnv.frm), true);
    saveEnv.state.dirty = true;
    saveEnv.setSaveMode("pending");
    const save = edit.saveEditing(saveEnv.frm);
    saveEnv.window.cur_frm = { doctype: "Door Cutting Order", doc: { name: "DCO-PLAN-B" } };
    saveEnv.pendingSave.resolve({});
    assert.equal(await save, false, "a late Plan save from A must not close or refresh a new document session");
    assert.equal(saveEnv.state.editing, true, "the stale adapter must not cancel the current draft projection");
    assert.equal(saveEnv.cancelCalls(), 0);
    assert.equal(saveEnv.loadCalls(), 0, "stale save must not trigger a force reload");
    assert.equal(saveEnv.alerts.length, 0, "stale save must not show a success alert");
}

run().then(() => console.log("plan edit-session lifecycle tests passed"));
