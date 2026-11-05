"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

function source(file) {
    return fs.readFileSync(
        path.resolve(__dirname, "../../public/js/door_cutting_order", file),
        "utf8",
    );
}

function baseline() {
    return {
        packing_mode: "smart",
        cutting_machine_type: "Auto",
        kerf_mm: 3,
        trim_margin_mm: 5,
        optimization_time_limit_sec: 30,
        liner_tool_diameter_mm: 3,
        handle_recess_tool_diameter_mm: 6,
        rear_groove_tool_diameter_mm: 5,
    };
}

function receipt() {
    return {
        exact_preview_commit: true,
        committed_preview_id: "D",
        name: "DCO-1",
        cutting_plan: "CP-SYSTEM",
        plan_revision: 1,
        plan_source_type: "System",
        plan_status: "Draft",
        ...baseline(),
    };
}

function environment() {
    const calls = [];
    let displayed = {
        name: "CP-SYSTEM",
        source_type: "System",
        status: "Draft",
        settings: baseline(),
    };
    const frm = {
        doctype: "Door Cutting Order",
        doc: { doctype: "Door Cutting Order", name: "DCO-1", docstatus: 0, status: "Draft" },
        __generation: 1,
        fields_dict: {},
        is_new() { return false; },
        is_dirty() { return false; },
        trigger() {},
    };
    const fakeWindow = {
        cur_frm: frm,
        addEventListener() {},
        dispatchEvent() {},
        requestAnimationFrame(callback) { callback(); },
        AlmdinaDocumentContext: {
            formIdentity(form) { return `Door Cutting Order::${form.doc.name}`; },
            capture(form) { return { identity: this.formIdentity(form), generation: form.__generation }; },
            isSameDocument(form, token) { return this.formIdentity(form) === token.identity; },
            isCurrent(form, token) {
                return fakeWindow.cur_frm === form
                    && this.isSameDocument(form, token)
                    && form.__generation === token.generation;
            },
            scheduleFrame(_form, _key, callback) { callback(); return 1; },
        },
        AlmdinaPermissions: { canDocument() { return true; } },
        AlmdinaPlanFieldAccessAdapter: { apply() {} },
        AlmdinaPlanWorkspacePresenterAdapter: {
            activeSettings() { return baseline(); },
            project() {},
        },
        AlmdinaPlanPreviewPresenter: {
            renderActionMessage() {},
            renderPreviewPlan() {},
            renderPersistedEditingState() {},
            restorePersistedPresentation() {},
        },
        AlmdinaPlanWorkspaceAPI: {
            saveSettings(name, settings) {
                calls.push(["saveSettings", name, { ...settings }]);
                displayed = {
                    name: "CP-SYSTEM",
                    source_type: "System",
                    status: "Draft",
                    settings: { ...baseline(), ...settings },
                };
                return Promise.resolve({
                    cutting_plan: "CP-SYSTEM",
                    changed_fields: Object.keys(settings),
                    plan_needs_recalculation: 0,
                });
            },
            commitPreview(name, id, candidateId, tools) {
                calls.push(["commit", id, tools ? { ...tools } : null]);
                return Promise.resolve({ ...receipt(), kerf_mm: 4 });
            },
            preview(_name, requested) {
                return Promise.resolve({
                    preview_id: "D",
                    order_name: "DCO-1",
                    plan: { sheets: [{}] },
                    source_plan_name: "CP-SYSTEM",
                    source_plan_revision: 1,
                    source_plan_modified: "before",
                    summary: {
                        settings: requested,
                        validation: { status: "Valid", needs_recalculation: false },
                    },
                });
            },
            load(name) {
                calls.push(["load", name]);
                return Promise.resolve({ plans: { system_draft: displayed } });
            },
        },
    };
    const frappe = {
        ui: { form: { on() {} } },
        utils: { escape_html: String },
        msgprint() {},
        show_alert() {},
    };
    const document = {
        getElementById() { return { remove() {} }; },
        createElement() { return {}; },
        head: { appendChild() {} },
        body: { classList: { toggle() {} } },
    };
    const context = vm.createContext({
        window: fakeWindow,
        document,
        frappe,
        $: (item) => item,
        __: String,
        console,
        CustomEvent: class {
            constructor(name, options) {
                this.name = name;
                this.detail = options && options.detail;
            }
        },
        structuredClone,
        Promise,
        Set,
        WeakMap,
        Map,
        Object,
        String,
        Number,
        Boolean,
    });
    fakeWindow.window = fakeWindow;
    for (const file of [
        "core/door_cutting_order_workspace_store.js",
        "core/door_cutting_order_edit_session_coordinator.js",
        "cutting_plan/door_cutting_order_plan_edit_session_ux.js",
        "cutting_plan/door_cutting_order_plan_preview_session.js",
        "cutting_plan/door_cutting_order_plan_preview_edit_ux.js",
        "cutting_plan/door_cutting_order_plan_settings_summary_ux.js",
    ]) {
        vm.runInContext(source(file), context, { filename: file });
    }
    const store = fakeWindow.AlmdinaWorkspaceStore.create("plan");
    const requestId = store.beginLoad("Door Cutting Order::DCO-1");
    store.resolveLoad("Door Cutting Order::DCO-1", requestId, {
        approved_plan: "CP-APPROVED",
        order_name: "DCO-1",
        editable_settings: baseline(),
        plans: { system_draft: { name: "CP-SYSTEM", revision: 1, settings: baseline() } },
    });
    fakeWindow.AlmdinaPlanWorkspaceState = {
        storeFor() { return store; },
        snapshot() { return store.snapshot(); },
        displayedPlan() { return displayed; },
        planForTab(_form, tab) {
            if (tab === "System") {
                return { name: "CP-SYSTEM", settings: displayed.settings };
            }
            return null;
        },
        load() {
            calls.push(["workspace-load"]);
            return Promise.resolve(store.snapshot());
        },
    };
    return { frm, store, calls, window: fakeWindow, displayed: () => displayed, setDisplayed(row) { displayed = row; } };
}

async function edit(env) {
    assert.equal(await env.window.AlmdinaDcoEditSessionCoordinator.start(env.frm, "plan"), true);
    assert.equal(env.store.snapshot().editing, true);
}

async function run() {
    const liner = environment();
    await edit(liner);
    liner.store.patchDraft({ liner_tool_diameter_mm: 4 });
    assert.equal(liner.window.AlmdinaPlanPreviewEditUX.canSaveEditing(liner.frm), true);
    assert.equal(await liner.window.AlmdinaDcoEditSessionCoordinator.save(liner.frm, "plan"), true);
    const saved = liner.calls.find((call) => call[0] === "saveSettings");
    assert.ok(saved, "diameter-only save must reach save_plan_settings");
    assert.equal(saved[2].liner_tool_diameter_mm, 4);
    assert.equal(saved[2].handle_recess_tool_diameter_mm, undefined);
    assert.equal(saved[2].rear_groove_tool_diameter_mm, undefined);
    assert.equal(liner.calls.some((call) => call[0] === "commit"), false);
    assert.equal(liner.window.AlmdinaPlanSettingsSummaryUX.displayedSettings(liner.frm).liner_tool_diameter_mm, 4);
    liner.window.AlmdinaPlanWorkspaceState.load();
    assert.equal(liner.window.AlmdinaPlanSettingsSummaryUX.displayedSettings(liner.frm).liner_tool_diameter_mm, 4);

    const handle = environment();
    await edit(handle);
    handle.store.patchDraft({ handle_recess_tool_diameter_mm: 8 });
    assert.equal(await handle.window.AlmdinaDcoEditSessionCoordinator.save(handle.frm, "plan"), true);
    assert.equal(handle.displayed().settings.handle_recess_tool_diameter_mm, 8);
    assert.equal(handle.displayed().settings.liner_tool_diameter_mm, 3);
    assert.equal(handle.window.AlmdinaPlanSettingsSummaryUX.displayedSettings(handle.frm).handle_recess_tool_diameter_mm, 8);

    const groove = environment();
    await edit(groove);
    groove.store.patchDraft({ rear_groove_tool_diameter_mm: 3 });
    assert.equal(await groove.window.AlmdinaDcoEditSessionCoordinator.save(groove.frm, "plan"), true);
    const grooveSave = groove.calls.find((call) => call[0] === "saveSettings");
    assert.equal(grooveSave[2].rear_groove_tool_diameter_mm, 3);
    assert.equal(grooveSave[2].liner_tool_diameter_mm, undefined);
    assert.equal(groove.displayed().settings.liner_tool_diameter_mm, 3);
    assert.equal(groove.displayed().settings.handle_recess_tool_diameter_mm, 6);
    assert.equal(groove.displayed().settings.rear_groove_tool_diameter_mm, 3);

    const all = environment();
    await edit(all);
    all.store.patchDraft({
        liner_tool_diameter_mm: 4,
        handle_recess_tool_diameter_mm: 8,
        rear_groove_tool_diameter_mm: 3,
    });
    assert.equal(await all.window.AlmdinaDcoEditSessionCoordinator.save(all.frm, "plan"), true);
    const allSave = all.calls.find((call) => call[0] === "saveSettings");
    assert.equal(allSave[2].liner_tool_diameter_mm, 4);
    assert.equal(allSave[2].handle_recess_tool_diameter_mm, 8);
    assert.equal(allSave[2].rear_groove_tool_diameter_mm, 3);
    const shown = all.window.AlmdinaPlanSettingsSummaryUX.displayedSettings(all.frm);
    assert.equal(shown.liner_tool_diameter_mm, 4);
    assert.equal(shown.handle_recess_tool_diameter_mm, 8);
    assert.equal(shown.rear_groove_tool_diameter_mm, 3);

    const identity = environment();
    await edit(identity);
    identity.store.patchDraft({ liner_tool_diameter_mm: 4 });
    assert.equal(await identity.window.AlmdinaDcoEditSessionCoordinator.save(identity.frm, "plan"), true);
    identity.setDisplayed({
        name: "CP-APPROVED",
        source_type: "System",
        status: "Approved",
        settings: baseline(),
    });
    assert.equal(identity.window.AlmdinaPlanSettingsSummaryUX.displayedSettings(identity.frm).liner_tool_diameter_mm, 3);
    identity.setDisplayed({
        name: "CP-SYSTEM",
        source_type: "System",
        status: "Draft",
        settings: { ...baseline(), liner_tool_diameter_mm: 4 },
    });
    assert.equal(identity.window.AlmdinaPlanSettingsSummaryUX.displayedSettings(identity.frm).liner_tool_diameter_mm, 4);

    const mixed = environment();
    await edit(mixed);
    assert.equal(await mixed.window.AlmdinaPlanPreviewSession.preview(mixed.frm, baseline()), true);
    mixed.store.patchDraft({ kerf_mm: 4, liner_tool_diameter_mm: 4 });
    assert.equal(await mixed.window.AlmdinaPlanPreviewSession.preview(mixed.frm, {
        ...baseline(),
        kerf_mm: 4,
        liner_tool_diameter_mm: 4,
    }), true);
    assert.equal(await mixed.window.AlmdinaDcoEditSessionCoordinator.save(mixed.frm, "plan"), true);
    const commit = mixed.calls.find((call) => call[0] === "commit");
    assert.ok(commit, "a nesting change still commits the preview");
    assert.equal(commit[2].liner_tool_diameter_mm, 4);
    assert.equal(mixed.calls.some((call) => call[0] === "saveSettings"), false);
}

run().then(() => console.log("tool diameter save tests passed"))
    .catch((error) => {
        console.error(error);
        process.exitCode = 1;
    });
