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
        attr() { return this; }, html(value) { if (value !== undefined) html = value; return this; },
        find() { return blank; },
    };
    const frm = { doctype: "Door Cutting Order", doc: { name: "DCO-1", system_plan_json: { sheets: [{ id: "canonical" }] } },
        fields_dict: { cutting_plan_html: { $wrapper: wrapper } } };
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

    const a = preview.preview(frm, settings("auto_pro"));
    preview.invalidate(frm);
    const b = preview.preview(frm, settings("optimal"));
    calls[1].job.resolve(response("B", calls[1].requested));
    assert.equal(await b, true);
    calls[0].job.resolve(response("A", calls[0].requested));
    assert.equal(await a, false);
    assert.equal(preview.snapshot(frm).previewId, "B");
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

    // A changed setting invalidates the request even when it is still in flight.
    preview.invalidate(frm);
    const c = preview.preview(frm, settings("deep"));
    preview.invalidate(frm);
    calls[2].job.resolve(response("C", calls[2].requested));
    assert.equal(await c, false);
    assert.equal(preview.isReady(frm), false);

    // A backend response for different settings cannot enable Save.
    const mismatched = preview.preview(frm, settings("optimal"));
    calls[3].job.resolve(response("wrong-settings", settings("auto_pro")));
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
    calls[4].job.resolve(response("D", calls[4].requested));
    assert.equal(await d, true);
    assert.equal((await preview.commit(frm)), true);
    assert.equal(calls.at(-1).commit, "D");
    assert.equal(calls.filter(call => call.requested).length, 5);

    // Identity changes invalidate pending responses independently of reset.
    const e = preview.preview(frm, settings("optimal"));
    frm.doc.name = "DCO-2";
    calls[6].job.resolve(response("E", calls[6].requested));
    assert.equal(await e, false);
    assert.equal(preview.isReady(frm), false);
    assert.ok(events.length);
}

run().catch(error => { console.error(error); process.exitCode = 1; });
