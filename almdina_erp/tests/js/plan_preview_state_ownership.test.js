"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.resolve(__dirname, "../../public/js/door_cutting_order");
const read = file => fs.readFileSync(path.join(root, file), "utf8");
const pending = () => {
    let resolve;
    const promise = new Promise(done => { resolve = done; });
    return { promise, resolve };
};
const settings = mode => ({
    packing_mode: mode, cutting_machine_type: "saw", kerf_mm: 3,
    trim_margin_mm: 5, optimization_time_limit_sec: 30,
});
const response = (id, requested) => ({
    preview_id: id,
    plan: { sheets: [{ id }], margin_policy: { notes: [id] }, method: id },
    summary: { settings: requested, validation: { status: "Valid", needs_recalculation: false } },
});

async function run() {
    const calls = [];
    const events = [];
    let html = "";
    const blank = { length: 0, on() { return this; }, each() { return this; } };
    const wrapper = {
        attributes: {},
        attr(name, value) {
            if (value === undefined) return this.attributes[name];
            this.attributes[name] = value;
            return this;
        },
        html(value) { if (value !== undefined) html = value; return html; },
        empty() { html = ""; },
        find(selector) {
            return { ...blank, length: html.includes(selector.replace(/^\./, "")) ? 1 : 0 };
        },
        children() { return { length: html ? 1 : 0 }; },
    };
    const frm = { doctype: "Door Cutting Order", doc: { name: "DCO-1", system_plan_json: { sheets: [{ id: "canonical" }] } },
        layout: { current_tab: { df: { fieldname: "results_tab" } } },
        fields_dict: { cutting_plan_html: { $wrapper: wrapper, df: {} } } };
    const window = {
        cur_frm: frm, dispatchEvent(event) { events.push(event); },
        AlmdinaDocumentContext: { formIdentity(form) { return `DCO::${form.doc.name}`; } },
        AlmdinaPlanWorkspaceAPI: {
            preview(_name, requested) { const job = pending(); calls.push({ job, requested }); return job.promise; },
            commitPreview(_name, id) { calls.push({ commit: id }); return Promise.resolve(true); },
            load() { return Promise.resolve({ plans: { system_draft: { snapshot_json: frm.doc.system_plan_json } } }); },
        },
        AlmdinaPermissions: { canDocument() { return true; } },
        AlmdinaCuttingPlanRender: { build(_frm, plan) { return `<geometry id="${plan.sheets[0].id}"></geometry>`; } },
        AlmdinaPlanEditSessionUX: { isEditing() { return true; } },
        addEventListener() {}, requestAnimationFrame(callback) { callback(); },
        setTimeout() { return 1; }, clearTimeout() {},
    };
    const context = vm.createContext({ window, CustomEvent: class { constructor(name, options) { this.name = name; this.detail = options.detail; } },
        frappe: { msgprint() {}, utils: { escape_html: String }, ui: { form: { on() {} } } }, __: String, console, structuredClone });
    vm.runInContext(read("core/door_cutting_order_workspace_store.js"), context);
    window.AlmdinaWorkspaceStore = context.window.AlmdinaWorkspaceStore;
    vm.runInContext(read("cutting_plan/door_cutting_order_plan_preview_session.js"), context);
    vm.runInContext(read("cutting_plan/door_cutting_order_plan_workspace_state.js"), context);
    vm.runInContext(read("cutting_plan/door_cutting_order_plan_tabs_ux.js"), context);
    vm.runInContext(read("cutting_plan/door_cutting_order_plan_content_ux.js"), context);
    vm.runInContext(read("cutting_plan/door_cutting_order_plan_workspace_presenter_adapter.js"), context);
    const preview = window.AlmdinaPlanPreviewSession;
    const workspace = window.AlmdinaPlanWorkspaceState;
    await workspace.load(frm);

    const mutableA = settings("auto_pro");
    const a = preview.preview(frm, mutableA);
    mutableA.packing_mode = "optimal";
    assert.equal(calls[0].requested.packing_mode, "auto_pro", "request settings must be copied before dispatch");
    preview.invalidate(frm);
    const b = preview.preview(frm, settings("optimal"));
    calls[1].job.resolve(response("B", calls[1].requested));
    assert.equal(await b, true);
    calls[0].job.resolve(response("A", calls[0].requested));
    assert.equal(await a, false);
    assert.equal(preview.snapshot(frm).previewId, "B");
    assert.equal(preview.isCommittable(frm), true);
    assert.equal(workspace.displayedPlanForTab(frm, "System").snapshot_json.sheets[0].id, "B");
    assert.equal(workspace.planForTab(frm, "System").snapshot_json.sheets[0].id, "canonical");
    const tabs = window.AlmdinaPlanTabsUX;
    for (let attempt = 0; attempt < 3; attempt += 1) {
        tabs.renderDualTabs(frm);
        assert.match(html, /<geometry id="B">/);
        assert.doesNotMatch(html, /<geometry id="canonical">/);
        const contentPlan = window.AlmdinaPlanContentUX.parsePlanSnapshot(frm);
        assert.equal(contentPlan.sheets[0].id, "B");
        assert.equal(contentPlan.margin_policy.notes[0], "B");
        assert.equal(contentPlan.method, "B");
    }

    // Exercise the real Surface Recovery orchestrator after a wiped plan DOM.
    let actionHtml = "";
    const actions = {
        attributes: {},
        attr(name, value) {
            if (value === undefined) return this.attributes[name];
            this.attributes[name] = value;
            return this;
        },
        html(value) { if (value !== undefined) actionHtml = value; return actionHtml; },
        find(selector) { return { length: actionHtml.includes(selector.replace(/^\./, "")) ? 1 : 0 }; },
        children() { return { length: actionHtml ? 1 : 0 }; },
    };
    frm.fields_dict.plan_control_actions = { $wrapper: actions, df: {} };
    window.AlmdinaPermissions.version = () => 1;
    window.AlmdinaCuttingPlanPieceGeometry = {};
    window.AlmdinaDoorCuttingPlanUX = { refresh() { actions.html('<div class="dco-plan-actions-shell"></div>'); } };
    window.AlmdinaPlanControlsUX = { apply() {} };
    const realContent = window.AlmdinaPlanContentUX;
    window.AlmdinaPlanContentUX = { apply() {}, isReady() { return true; } };
    vm.runInContext(read("cutting_plan/door_cutting_order_plan_surface_bootstrap.js"), context);
    wrapper.empty();
    assert.equal(await window.AlmdinaCuttingPlanSurfaceBootstrap.recover(frm), true);
    assert.match(html, /<geometry id="B">/);
    assert.doesNotMatch(html, /<geometry id="canonical">/);
    window.AlmdinaPlanContentUX = realContent;

    // A changed setting invalidates the request even when it is still in flight.
    preview.invalidate(frm);
    const c = preview.preview(frm, settings("deep"));
    preview.invalidate(frm);
    calls[2].job.resolve(response("C", calls[2].requested));
    assert.equal(await c, false);
    assert.equal(preview.isReady(frm), false);

    const obsoleteFailure = preview.preview(frm, settings("auto_pro"));
    preview.invalidate(frm);
    const newer = preview.preview(frm, settings("optimal"));
    calls[4].job.resolve(response("newer", calls[4].requested));
    assert.equal(await newer, true);
    calls[3].job.resolve(Promise.reject(new Error("obsolete network failure")));
    assert.equal(await obsoleteFailure, false);
    assert.equal(preview.snapshot(frm).previewId, "newer");

    // A backend response for different settings cannot enable Save.
    const mismatched = preview.preview(frm, settings("optimal"));
    calls[5].job.resolve(response("wrong-settings", settings("auto_pro")));
    await assert.rejects(mismatched, /settings do not match/);
    assert.equal(preview.isCommittable(frm), false);

    // Canonical refresh is deferred while a Plan draft is being edited.
    const store = workspace.storeFor(frm);
    store.beginEdit(settings("auto_pro"));
    store.patchDraft({ packing_mode: "optimal" });
    const before = store.snapshot();
    await workspace.load(frm, { force: true });
    const after = store.snapshot();
    assert.deepEqual(after.draft, before.draft);
    assert.equal(after.editing, true);
    assert.equal(after.dirty, true);
    assert.equal(after.freshness, "stale");
    store.cancelEdit();
    await workspace.load(frm, { force: true });
    assert.equal(store.snapshot().freshness, "fresh");

    const d = preview.preview(frm, settings("optimal"));
    calls[6].job.resolve(response("D", calls[6].requested));
    assert.equal(await d, true);
    assert.equal((await preview.commit(frm)), true);
    assert.equal(calls.at(-1).commit, "D");
    assert.equal(calls.filter(call => call.requested).length, 7);

    // Identity changes invalidate pending responses independently of reset.
    const e = preview.preview(frm, settings("optimal"));
    frm.doc.name = "DCO-2";
    calls[8].job.resolve(response("E", calls[8].requested));
    assert.equal(await e, false);
    assert.equal(preview.isReady(frm), false);
    assert.ok(events.length);
}

run().catch(error => { console.error(error); process.exitCode = 1; });
